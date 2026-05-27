"""RC Russell Dodge Agent — scoring and email drafting pipeline.

This module implements the core agent logic:
1. Pull projects from Dodge matching RC Russell's geographic/stage criteria
2. Score each project against the RC Russell profile using an LLM
3. Filter to qualified projects (score >= 7)
4. Draft outreach emails for qualified projects
5. Generate a report with all drafts

Designed to be called from a Cowork scheduled task or run standalone.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .client import DodgeClient

# ---------------------------------------------------------------------------
# Prompts (from the Dodge Agent Build Kit)
# ---------------------------------------------------------------------------

SCORING_SYSTEM_PROMPT = """You are evaluating a new Dodge Construction project for fit against RC Russell Management's capabilities. Use the structured profile and the explicit criteria to score this opportunity.

RC RUSSELL PROFILE:
{profile_markdown}

DODGE PROJECT DATA:
{project_json}

Return JSON with these fields:
{{
  "score": <0-10 integer>,
  "would_pursue": <true / false>,
  "match_reasons": [<list of 2-4 specific reasons this matches RC Russell's criteria — cite the project data, don't be generic>],
  "disqualifiers": [<list of any reasons this doesn't fit; empty list if none>],
  "key_uncertainties": [<things a human reviewer should verify before bidding; empty list if none>],
  "recommended_contact_role": <who to reach out to first — owner, architect, GC, developer, etc.>,
  "estimated_project_size_usd": <number or null>,
  "primary_location": <city, state>,
  "project_type": <new_construction / renovation / mixed / other>,
  "role_fit": <GC / owners_rep / CM / design_build / both / neither>
}}

SCORING RUBRIC:
- 9–10: All hard criteria met PLUS a strong positive signal (size in sweet spot, similar to past projects, prestigious owner, etc.)
- 7–8: All hard criteria met, no standout positive signal
- 5–6: Hard criteria mostly met but one ambiguous element (uncertain budget, mixed project type, ambiguous role)
- 3–4: Two or more hard criteria fail OR project appears to be a take-over
- 0–2: Multiple hard criteria fail OR an explicit disqualifier is present

HARD DISQUALIFIERS — set score to 0–2 AND would_pursue to false if ANY are true:
- Project is outside NY, NJ, or CT
- Project is a take-over (another GC was removed)
- New construction project with budget below $20M
- Role is neither GC nor Owner's Representative nor CM nor Design/Build Manager (e.g., subcontracting bid only)

Be specific. Reasons must cite the project data, not generic capability claims.
Return ONLY valid JSON, no markdown fences or extra text."""


EMAIL_DRAFTING_PROMPT = """You are drafting a cold proposal email from RC Russell Management to a named contact on a Dodge Construction project. The email is a DRAFT for human review — RC Russell's team will edit and send manually. Do not assume it will be sent as-is.

RC RUSSELL PROFILE:
{profile_markdown}

PROJECT DATA:
{project_json}

CONTACT DATA:
{contact_json}

MATCH REASONS (from scoring agent):
{match_reasons}

Output as JSON:
{{
  "to": <contact email or empty string if not found>,
  "to_name": <contact name or firm name>,
  "subject": <short, specific subject line — reference the project name or location, never generic>,
  "body": <full email body, see structure below>,
  "attachment_note": "RC Russell Management corporate brochure — attach manually before sending",
  "internal_note": <any flags for the human reviewer — e.g., 'verify project budget before sending' or 'contact email looks like info@ — confirm before sending' — empty string if none>
}}

EMAIL BODY STRUCTURE (in this order, no headings):
1. Personalized opening — 1 sentence referencing the specific project, location, or context. Never "I hope this finds you well."
2. Why RC Russell is reaching out about THIS project specifically — 2–3 sentences, cite the match reasons concretely (geography, size, project type, owner reputation).
3. One sentence of credibility — name a relevant past project from RC Russell's portfolio that maps to this opportunity.
4. Specific ask — 1–2 sentences: either a 20-minute intro call or to be considered in the bid process.
5. Soft close — note the brochure attached for reference, then sign off with the profile's email signature.

CONSTRAINTS:
- Body maximum 150 words
- No buzzwords ("synergy", "leverage", "best-in-class", "world-class", "trusted partner")
- No apologetic openings ("I just wanted to reach out", "I hope I'm not bothering you")
- No marketing copy about generic capabilities — only specific, relevant claims tied to this project
- Match RC Russell's voice from the profile: professional, direct, no fluff
- If the contact name is missing or generic (info@, sales@), set "to" to the email but add a flag to internal_note

A reader with no prior knowledge of RC Russell should still understand within 30 seconds why this email is relevant to their project.
Return ONLY valid JSON, no markdown fences or extra text."""


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------

def load_profile(profile_path: str | None = None) -> str:
    """Load the RC Russell profile markdown."""
    if profile_path is None:
        # Default: look next to this file or in the project root
        candidates = [
            Path(__file__).parent.parent.parent / "rc_russell_profile.md",
            Path.home() / "rcr-dodge-agent" / "dodge-mcp-server" / "rc_russell_profile.md",
        ]
        for p in candidates:
            if p.exists():
                return p.read_text()
        raise FileNotFoundError(
            "rc_russell_profile.md not found. Provide profile_path or place it in the project root."
        )
    return Path(profile_path).read_text()


# ---------------------------------------------------------------------------
# Project fetching
# ---------------------------------------------------------------------------

async def fetch_candidate_projects(
    client: DodgeClient,
    days_back: int = 7,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Fetch recent projects in NJ/NY/CT that might fit RC Russell."""
    from .server import _flatten_project

    publish_min = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    publish_max = datetime.now().strftime("%Y-%m-%d")

    result = await client.search_projects(
        states=["NJ", "NY", "CT"],
        stage_categories=["Design", "Bidding/Negotiating"],
        value_min=10_000_000,  # Cast a slightly wider net than the $20M floor — scoring will filter
        work_types=["New Project", "Additions", "Alterations"],
        publish_date_min=publish_min,
        publish_date_max=publish_max,
        sort_field="ProjectValue",
        sort_order="DESC",
        limit=limit,
    )

    projects_raw = result.get("projects", [])
    return [_flatten_project(p) for p in projects_raw]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def build_scoring_prompt(profile: str, project: dict[str, Any]) -> str:
    """Build the scoring prompt for a single project."""
    return SCORING_SYSTEM_PROMPT.format(
        profile_markdown=profile,
        project_json=json.dumps(project, indent=2, default=str),
    )


def parse_scoring_response(response_text: str) -> dict[str, Any]:
    """Parse the LLM scoring response into a dict."""
    # Strip markdown fences if present
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# Email drafting
# ---------------------------------------------------------------------------

def pick_best_contact(project: dict[str, Any], scoring: dict[str, Any]) -> dict[str, Any]:
    """Pick the best contact from the project for outreach."""
    contacts = project.get("contacts", [])
    if not contacts:
        return {
            "firmName": "Unknown",
            "contactName": "[PLACEHOLDER — contact not found in Dodge data]",
            "email": "",
            "role": "Unknown",
        }

    recommended_role = scoring.get("recommended_contact_role", "owner").lower()

    # Priority order for outreach
    role_priority = ["owner", "developer", "architect", "engineer", "consultant"]

    # Try to match recommended role first
    for c in contacts:
        role = (c.get("role") or "").lower()
        category = (c.get("category") or "").lower()
        if recommended_role in role or recommended_role in category:
            return c

    # Fall back to priority order
    for priority_role in role_priority:
        for c in contacts:
            role = (c.get("role") or "").lower()
            category = (c.get("category") or "").lower()
            if priority_role in role or priority_role in category:
                return c

    # Last resort: first contact
    return contacts[0]


def build_email_prompt(
    profile: str,
    project: dict[str, Any],
    contact: dict[str, Any],
    match_reasons: list[str],
) -> str:
    """Build the email drafting prompt."""
    return EMAIL_DRAFTING_PROMPT.format(
        profile_markdown=profile,
        project_json=json.dumps(project, indent=2, default=str),
        contact_json=json.dumps(contact, indent=2, default=str),
        match_reasons=json.dumps(match_reasons, indent=2),
    )


def parse_email_response(response_text: str) -> dict[str, Any]:
    """Parse the LLM email drafting response."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    scored_projects: list[dict[str, Any]],
    email_drafts: list[dict[str, Any]],
    run_date: str,
    total_fetched: int,
    total_qualified: int,
) -> str:
    """Generate the markdown report for the team."""
    lines = [
        f"# Dodge Agent Report — {run_date}",
        "",
        f"**Projects pulled:** {total_fetched}",
        f"**Projects qualified (score >= 7):** {total_qualified}",
        f"**Email drafts generated:** {len(email_drafts)}",
        "",
        "---",
        "",
    ]

    for i, (proj, scoring, draft) in enumerate(
        zip(
            [sp["project"] for sp in scored_projects if sp["scoring"].get("would_pursue")],
            [sp["scoring"] for sp in scored_projects if sp["scoring"].get("would_pursue")],
            email_drafts,
        ),
        1,
    ):
        lines.extend([
            f"## {i}. {proj.get('projectName', 'Unknown Project')}",
            "",
            f"**Location:** {proj.get('city', '?')}, {proj.get('state', '?')}",
            f"**Dodge Report #:** {proj.get('dodgeReportNumber', 'N/A')}",
            f"**Valuation:** ${proj.get('valueLow', 0):,.0f}" + (f" – ${proj.get('valueHigh', 0):,.0f}" if proj.get('valueHigh') else ""),
            f"**Stage:** {', '.join(proj.get('stages', ['N/A']))}",
            f"**Type:** {proj.get('primaryProjectType', 'N/A')}",
            f"**Work Type:** {', '.join(proj.get('workTypes', ['N/A']))}",
            f"**Score:** {scoring.get('score', 'N/A')}/10",
            f"**Role Fit:** {scoring.get('role_fit', 'N/A')}",
            "",
            "### Match Reasons",
            "",
        ])
        for reason in scoring.get("match_reasons", []):
            lines.append(f"- {reason}")

        if scoring.get("key_uncertainties"):
            lines.extend(["", "### Uncertainties (verify before sending)", ""])
            for u in scoring["key_uncertainties"]:
                lines.append(f"- {u}")

        lines.extend([
            "",
            "### Draft Email",
            "",
            f"**To:** {draft.get('to_name', 'N/A')} ({draft.get('to', 'email not found')})",
            f"**Subject:** {draft.get('subject', '')}",
            "",
            "```",
            draft.get("body", ""),
            "```",
            "",
            f"**Attachment reminder:** {draft.get('attachment_note', '')}",
        ])

        if draft.get("internal_note"):
            lines.append(f"**Internal note:** {draft['internal_note']}")

        lines.extend(["", "---", ""])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone runner (for testing or cron)
# ---------------------------------------------------------------------------

async def run_agent(
    api_key: str | None = None,
    profile_path: str | None = None,
    output_dir: str | None = None,
    days_back: int = 7,
    score_threshold: int = 7,
    llm_call: Any = None,
) -> dict[str, Any]:
    """Run the full agent pipeline.

    Args:
        api_key: Dodge API key (or set DODGE_API_KEY env var)
        profile_path: Path to rc_russell_profile.md
        output_dir: Where to write the report and drafts
        days_back: How many days back to search for new projects
        score_threshold: Minimum score to qualify (default 7)
        llm_call: Async callable(prompt: str) -> str for LLM inference.
                  If None, returns projects without scoring (useful for testing API).

    Returns:
        Summary dict with counts and file paths.
    """
    key = api_key or os.environ.get("DODGE_API_KEY", "")
    if not key:
        raise RuntimeError("DODGE_API_KEY required")

    profile = load_profile(profile_path)
    client = DodgeClient(api_key=key)
    run_date = datetime.now().strftime("%Y-%m-%d")

    try:
        # 1. Fetch candidates
        projects = await fetch_candidate_projects(client, days_back=days_back)
        total_fetched = len(projects)

        if not projects:
            return {
                "run_date": run_date,
                "total_fetched": 0,
                "total_qualified": 0,
                "drafts_generated": 0,
                "message": "No projects found matching criteria.",
            }

        # 2. Score (if LLM is available)
        scored: list[dict[str, Any]] = []
        if llm_call:
            for proj in projects:
                prompt = build_scoring_prompt(profile, proj)
                response = await llm_call(prompt)
                try:
                    scoring = parse_scoring_response(response)
                except json.JSONDecodeError:
                    scoring = {"score": 0, "would_pursue": False, "match_reasons": [], "disqualifiers": ["Failed to parse scoring response"], "key_uncertainties": []}
                scored.append({"project": proj, "scoring": scoring})
        else:
            # No LLM — return raw projects for review
            return {
                "run_date": run_date,
                "total_fetched": total_fetched,
                "total_qualified": "N/A (no LLM provided)",
                "drafts_generated": 0,
                "projects": projects,
                "message": "Projects fetched but not scored (no LLM callable provided).",
            }

        # 3. Filter qualified
        qualified = [s for s in scored if s["scoring"].get("score", 0) >= score_threshold and s["scoring"].get("would_pursue")]
        total_qualified = len(qualified)

        # 4. Draft emails for qualified projects
        email_drafts: list[dict[str, Any]] = []
        for q in qualified:
            contact = pick_best_contact(q["project"], q["scoring"])
            prompt = build_email_prompt(
                profile,
                q["project"],
                contact,
                q["scoring"].get("match_reasons", []),
            )
            response = await llm_call(prompt)
            try:
                draft = parse_email_response(response)
            except json.JSONDecodeError:
                draft = {
                    "to": contact.get("email", ""),
                    "to_name": contact.get("contactName") or contact.get("firmName", "Unknown"),
                    "subject": f"RC Russell — {q['project'].get('projectName', 'Project')}",
                    "body": "[Failed to generate draft — review project manually]",
                    "attachment_note": "Attach RC Russell brochure",
                    "internal_note": "Auto-draft failed; write manually",
                }
            email_drafts.append(draft)

        # 5. Generate report
        report = generate_report(
            scored_projects=qualified,
            email_drafts=email_drafts,
            run_date=run_date,
            total_fetched=total_fetched,
            total_qualified=total_qualified,
        )

        # 6. Write output
        if output_dir:
            out_path = Path(output_dir) / run_date
            out_path.mkdir(parents=True, exist_ok=True)

            # Write report
            report_file = out_path / "dodge_report.md"
            report_file.write_text(report)

            # Write individual drafts
            for j, (q, draft) in enumerate(zip(qualified, email_drafts), 1):
                proj_name = q["project"].get("projectName", "unknown").replace("/", "-").replace(" ", "_")[:50]
                contact_name = (draft.get("to_name") or "unknown").replace("/", "-").replace(" ", "_")[:30]
                draft_file = out_path / f"{j:02d}__{proj_name}__{contact_name}.md"

                draft_content = [
                    f"# {q['project'].get('projectName', 'Unknown')}",
                    "",
                    f"**Score:** {q['scoring'].get('score')}/10",
                    f"**Dodge Report #:** {q['project'].get('dodgeReportNumber')}",
                    f"**ATTACH RC RUSSELL BROCHURE PDF BEFORE SENDING**",
                    "",
                    f"**To:** {draft.get('to_name')} ({draft.get('to', 'email not found')})",
                    f"**Subject:** {draft.get('subject')}",
                    "",
                    draft.get("body", ""),
                    "",
                ]
                if draft.get("internal_note"):
                    draft_content.append(f"---\n**Internal note:** {draft['internal_note']}")

                draft_file.write_text("\n".join(draft_content))

            return {
                "run_date": run_date,
                "total_fetched": total_fetched,
                "total_qualified": total_qualified,
                "drafts_generated": len(email_drafts),
                "report_path": str(report_file),
                "output_dir": str(out_path),
            }

        return {
            "run_date": run_date,
            "total_fetched": total_fetched,
            "total_qualified": total_qualified,
            "drafts_generated": len(email_drafts),
            "report": report,
        }

    finally:
        await client.close()
