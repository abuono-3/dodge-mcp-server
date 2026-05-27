"""Dodge Construction Network MCP Server.

Exposes Dodge API endpoints as MCP tools so that AI agents
can search construction projects, companies, and documents.

Configuration via environment variables:
    DODGE_API_KEY  – required, your Dodge x-api-key
    DODGE_BASE_URL – optional, defaults to https://www.construction.com
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import DodgeClient, DodgeAPIError

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "dodge-construction",
    instructions="Search the Dodge Construction Network for projects, companies, and documents.",
)

_client: DodgeClient | None = None


def _get_client() -> DodgeClient:
    global _client
    if _client is None:
        api_key = os.environ.get("DODGE_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "DODGE_API_KEY environment variable is required. "
                "Set it to your Dodge Construction Network API key."
            )
        base_url = os.environ.get("DODGE_BASE_URL", "https://www.construction.com")
        _client = DodgeClient(api_key=api_key, base_url=base_url)
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_project(proj_kv: dict[str, Any]) -> dict[str, Any]:
    """Flatten a project key-value pair into a cleaner summary dict."""
    project_id = proj_kv.get("key", "")
    val = proj_kv.get("value", {})
    summary = val.get("summary", {})
    data = val.get("data", {})

    # Extract project name
    project_name_obj = data.get("projectName", {}) or {}
    project_name = project_name_obj.get("value", "Unknown")

    # Extract location
    locations = data.get("locations", {}) or {}
    addr = locations.get("projectAddress", {}) or {}
    city_obj = addr.get("city", {}) or {}
    state_obj = addr.get("stateID", {}) or {}
    county_obj = addr.get("county", {}) or {}
    addr_lines = addr.get("addressLines", {}) or {}
    line1_obj = addr_lines.get("line1", {}) or {}

    # Extract valuation
    valuation = data.get("valuation", {}) or {}

    # Extract stages
    stages = data.get("stages", []) or []
    stage_values = [s.get("value", "") for s in stages if s.get("value")]
    parent_stages = data.get("parentStages", []) or []
    parent_stage_values = [s.get("value", "") for s in parent_stages if s.get("value")]

    # Extract types
    types = data.get("types", []) or []
    type_values = [t.get("value", "") for t in types if t.get("value")]
    primary_type = next((t.get("value", "") for t in types if t.get("primary") == "Y"), "")

    # Extract work types
    work_types = data.get("workTypes", []) or []
    work_type_values = [w.get("value", "") for w in work_types if w.get("value")]

    # Extract contacts (summarized)
    contacts_raw = data.get("contacts", []) or []
    contacts = []
    for c in contacts_raw:
        contact_summary = {
            "firmName": c.get("firmName"),
            "contactName": c.get("contactName"),
            "contactTitle": c.get("contactTitle"),
            "role": (c.get("contactRole", {}) or {}).get("value"),
            "category": c.get("contactCategory"),
            "group": c.get("contactGroup"),
            "city": c.get("city"),
            "state": c.get("state"),
            "email": c.get("email"),
            "phone": f"{c.get('phoneAreaCode', '')}-{c.get('phoneNumber', '')}" if c.get("phoneNumber") else None,
            "url": c.get("url"),
        }
        # Remove None values for cleaner output
        contacts.append({k: v for k, v in contact_summary.items() if v})

    # Extract bid info
    bid_infos = data.get("bidInfos", {}) or {}
    bid_date_obj = bid_infos.get("bidDate", {}) or {}

    # Extract additional details
    additional = data.get("additionalDetails", {}) or {}
    delivery_obj = additional.get("deliverySys", {}) or {}
    owner_class_obj = additional.get("ownerClass", {}) or {}

    # Extract structural data
    details = data.get("details", {}) or {}
    structural = details.get("structuralData", {}) or {}
    sq_ft_obj = structural.get("squareFootage", {}) or {}
    stories_obj = structural.get("numberOfStories", {}) or {}

    # Extract notes/description
    description = details.get("stdInText", "")

    # Document counts
    doc_counts = summary.get("documentCounts", {}) or {}

    return {
        "projectId": project_id,
        "projectName": project_name,
        "dodgeReportNumber": summary.get("dodgeReportNumber"),
        "reportDate": summary.get("reportDate"),
        "firstReportDate": summary.get("firstReportDate"),
        "lastReportDate": summary.get("lastReportDate"),
        "address": line1_obj.get("value"),
        "city": city_obj.get("value"),
        "state": state_obj.get("value"),
        "county": county_obj.get("value"),
        "valueLow": valuation.get("valueLow"),
        "valueHigh": valuation.get("valueHigh"),
        "parentStages": parent_stage_values,
        "stages": stage_values,
        "primaryProjectType": primary_type,
        "projectTypes": type_values,
        "workTypes": work_type_values,
        "deliverySystem": delivery_obj.get("value"),
        "ownerClass": owner_class_obj.get("value"),
        "bidDate": bid_date_obj.get("value"),
        "squareFootage": sq_ft_obj.get("value"),
        "stories": stories_obj.get("value"),
        "description": description,
        "contacts": contacts,
        "documentCounts": doc_counts,
        "subProjectCount": summary.get("subProjectCount", 0),
    }


def _flatten_company(company: dict[str, Any]) -> dict[str, Any]:
    """Flatten a company item into a cleaner summary dict."""
    contacts = []
    for c in (company.get("contacts") or []):
        cs = {
            "name": c.get("name"),
            "title": c.get("title"),
            "email": c.get("email"),
            "phone": f"{c.get('areaCode', '')}-{c.get('phoneNumber', '')}" if c.get("phoneNumber") else None,
        }
        contacts.append({k: v for k, v in cs.items() if v})

    return {
        "companyId": company.get("id"),
        "firmName": company.get("firmName"),
        "address": company.get("addressLine1"),
        "city": company.get("cityName"),
        "state": company.get("stateAbbr"),
        "county": company.get("countyName"),
        "zipCode": company.get("zipCode5"),
        "phone": f"{company.get('phoneAreaCode', '')}-{company.get('phoneNbr', '')}" if company.get("phoneNbr") else None,
        "url": company.get("url"),
        "primaryGroup": company.get("primaryGroup"),
        "primaryRole": company.get("primaryRole"),
        "specialty": company.get("specialty"),
        "relatedProjectValue": company.get("relatedProjValue"),
        "projectCount": company.get("projCnt"),
        "contacts": contacts,
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_projects(
    states: list[str] | None = None,
    counties: list[str] | None = None,
    cities: list[str] | None = None,
    project_types: list[str] | None = None,
    work_types: list[str] | None = None,
    stage_categories: list[str] | None = None,
    stage_items: list[str] | None = None,
    value_min: int | None = None,
    value_max: int | None = None,
    publish_date_min: str | None = None,
    publish_date_max: str | None = None,
    bid_date_min: str | None = None,
    bid_date_max: str | None = None,
    keywords: str | None = None,
    ownership_types: list[str] | None = None,
    sort_field: str = "ProjectValue",
    sort_order: str = "DESC",
    offset: int = 0,
    limit: int = 25,
) -> str:
    """Search Dodge Construction Network for projects.

    Filter by location (states like "NJ", "NY"), project types (e.g. "Office",
    "Hospital"), stages (categories like "Design", "Bidding/Negotiating"),
    valuation range, date ranges, work types, and more.

    Common stage categories: Design, Bidding/Negotiating, Start, Completed
    Common stage items: Planning Schematics, Design Development,
        Construction Documents, GC Bidding, Bidding, Negotiating, Bid Results
    Common work types: New Project, Additions, Alterations
    Common ownership types: Private, State, Federal, County, City/Municipal

    Returns a list of projects with contacts, valuation, and location details.
    Note: Free trial is limited to 25 projects per day.
    """
    try:
        client = _get_client()
        result = await client.search_projects(
            states=states,
            counties=counties,
            cities=cities,
            project_types=project_types,
            work_types=work_types,
            stage_categories=stage_categories,
            stage_items=stage_items,
            value_min=value_min,
            value_max=value_max,
            publish_date_min=publish_date_min,
            publish_date_max=publish_date_max,
            bid_date_min=bid_date_min,
            bid_date_max=bid_date_max,
            keywords=keywords,
            ownership_types=ownership_types,
            sort_field=sort_field,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
        )

        total = result.get("total", 0)
        projects_raw = result.get("projects", [])
        projects = [_flatten_project(p) for p in projects_raw]

        return json.dumps(
            {"total": total, "returned": len(projects), "projects": projects},
            indent=2,
            default=str,
        )
    except DodgeAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
async def search_projects_raw(body: dict[str, Any]) -> str:
    """Send a raw search request to the Dodge project search API.

    Use this for advanced queries that need the full Dodge API request schema.
    The body should follow the Dodge API ProjectSearchRequest format with
    criteria, sorts, and pagination fields.

    Example body:
    {
        "criteria": {
            "location": {"state": ["NJ"]},
            "stage": {"categories": ["Design"]},
            "valueRange": {"min": 20000000}
        },
        "sorts": [{"field": "ProjectValue", "order": "DESC"}],
        "pagination": {"offset": 0, "limit": 25}
    }
    """
    try:
        client = _get_client()
        result = await client.search_projects_raw(body)

        total = result.get("total", 0)
        projects_raw = result.get("projects", [])
        projects = [_flatten_project(p) for p in projects_raw]

        return json.dumps(
            {"total": total, "returned": len(projects), "projects": projects},
            indent=2,
            default=str,
        )
    except DodgeAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
async def search_companies(
    keywords: str | None = None,
    company_search_area: list[str] | None = None,
    company_type_categories: list[str] | None = None,
    company_type_items: list[str] | None = None,
    states: list[str] | None = None,
    cities: list[str] | None = None,
    sort_field: str = "CompanyName",
    sort_order: str = "ASC",
    offset: int = 0,
    limit: int = 25,
) -> str:
    """Search Dodge Construction Network for companies and contacts.

    Filter by company name keywords, type (e.g. "General Contractor",
    "Architect"), and location. Returns company details including contacts
    with names, titles, emails, and phone numbers.

    Common company_search_area values: CompanyName
    Common company_type_categories: General Contractor, Architect,
        Engineer, Owner, Subcontractor
    """
    try:
        client = _get_client()
        result = await client.search_companies(
            keywords=keywords,
            company_search_area=company_search_area,
            company_type_categories=company_type_categories,
            company_type_items=company_type_items,
            states=states,
            cities=cities,
            sort_field=sort_field,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
        )

        total = result.get("total", 0)
        companies_raw = result.get("companies", [])
        companies = [_flatten_company(c) for c in companies_raw]

        return json.dumps(
            {"total": total, "returned": len(companies), "companies": companies},
            indent=2,
            default=str,
        )
    except DodgeAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
async def get_project_documents(project_id: str) -> str:
    """Get plans, specs, and addenda documents for a specific Dodge project.

    Provide a project ID (e.g. "202500377933") to retrieve available
    construction documents including plans, specs, and addenda with
    download URLs.
    """
    try:
        client = _get_client()
        result = await client.get_project_documents(project_id)
        return json.dumps(result, indent=2, default=str)
    except DodgeAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
async def get_spec_alert_names() -> str:
    """Get all available spec alert names from Dodge.

    Returns a list of spec alert identifiers that can be used
    to filter project searches by spec alerts.
    """
    try:
        client = _get_client()
        result = await client.get_spec_alert_names()
        return json.dumps(result, indent=2, default=str)
    except DodgeAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the Dodge MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
