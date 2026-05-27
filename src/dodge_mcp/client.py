"""Dodge Construction Network API client."""

from __future__ import annotations

import httpx
from typing import Any


BASE_URL = "https://www.construction.com"


class DodgeAPIError(Exception):
    """Raised when the Dodge API returns an error."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Dodge API error {status_code}: {detail}")


class DodgeClient:
    """Async client for the Dodge Construction Network API.

    Auth is via the ``x-api-key`` header.
    """

    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: float = 30.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self):
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(path, json=body)
        if resp.status_code != 200:
            raise DodgeAPIError(resp.status_code, resp.text[:500])
        return resp.json()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._client.get(path, params=params)
        if resp.status_code != 200:
            raise DodgeAPIError(resp.status_code, resp.text[:500])
        return resp.json()

    # ------------------------------------------------------------------
    # Project endpoints
    # ------------------------------------------------------------------

    async def search_projects(
        self,
        *,
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
        project_ids: list[str] | None = None,
        ownership_types: list[str] | None = None,
        active_only: bool = True,
        sort_field: str = "ProjectValue",
        sort_order: str = "DESC",
        offset: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search Dodge projects with rich filtering."""
        criteria: dict[str, Any] = {}

        if keywords:
            criteria["keywords"] = keywords
        if project_ids:
            criteria["projectIds"] = project_ids
        if active_only:
            criteria["activeProjectOnly"] = True

        # Location
        location: dict[str, Any] = {}
        if states:
            location["state"] = states
        if counties:
            location["county"] = counties
        if cities:
            location["city"] = cities
        if location:
            criteria["location"] = location

        # Stage
        if stage_categories or stage_items:
            stage: dict[str, Any] = {}
            if stage_categories:
                stage["categories"] = stage_categories
            if stage_items:
                stage["items"] = stage_items
            criteria["stage"] = stage

        # Project types, work types, ownership
        if project_types:
            criteria["projectTypes"] = project_types
        if work_types:
            criteria["workTypes"] = work_types
        if ownership_types:
            criteria["ownershipTypes"] = ownership_types

        # Value range
        if value_min is not None or value_max is not None:
            vr: dict[str, int] = {}
            if value_min is not None:
                vr["min"] = value_min
            if value_max is not None:
                vr["max"] = value_max
            criteria["valueRange"] = vr

        # Date ranges
        if publish_date_min or publish_date_max:
            dr: dict[str, str] = {}
            if publish_date_min:
                dr["min"] = publish_date_min
            if publish_date_max:
                dr["max"] = publish_date_max
            criteria["publishDateRange"] = dr

        if bid_date_min or bid_date_max:
            bdr: dict[str, str] = {}
            if bid_date_min:
                bdr["min"] = bid_date_min
            if bid_date_max:
                bdr["max"] = bid_date_max
            criteria["bidDateRange"] = bdr

        # Always filter to Project report type
        criteria["reportTypes"] = ["Project"]

        body: dict[str, Any] = {
            "criteria": criteria,
            "sorts": [{"field": sort_field, "order": sort_order}],
            "pagination": {"offset": offset, "limit": limit},
        }

        return await self._post("/api/1.0/int/project/search", body)

    async def search_projects_raw(self, body: dict[str, Any]) -> dict[str, Any]:
        """Send a raw project search request body (for advanced queries)."""
        return await self._post("/api/1.0/int/project/search", body)

    # ------------------------------------------------------------------
    # Company endpoints
    # ------------------------------------------------------------------

    async def search_companies(
        self,
        *,
        keywords: str | None = None,
        company_search_area: list[str] | None = None,
        company_ids: list[str] | None = None,
        company_type_categories: list[str] | None = None,
        company_type_items: list[str] | None = None,
        states: list[str] | None = None,
        cities: list[str] | None = None,
        sort_field: str = "CompanyName",
        sort_order: str = "ASC",
        offset: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search Dodge companies/contacts."""
        company_criteria: dict[str, Any] = {}

        if keywords:
            company_criteria["keywords"] = keywords
        if company_search_area:
            company_criteria["companySearchArea"] = company_search_area
        if company_ids:
            company_criteria["companyIds"] = company_ids

        # Company type
        if company_type_categories or company_type_items:
            ct: dict[str, Any] = {}
            if company_type_categories:
                ct["categories"] = company_type_categories
            if company_type_items:
                ct["items"] = company_type_items
            company_criteria["companyType"] = ct

        # Location
        location: dict[str, Any] = {}
        if states:
            location["state"] = states
        if cities:
            location["city"] = cities
        if location:
            company_criteria["location"] = location

        body: dict[str, Any] = {
            "criteria": {"company": company_criteria},
            "sorts": [{"field": sort_field, "order": sort_order}],
            "pagination": {"offset": offset, "limit": limit},
        }

        return await self._post("/api/1.0/int/company/search", body)

    # ------------------------------------------------------------------
    # Document endpoints
    # ------------------------------------------------------------------

    async def get_project_documents(self, project_id: str) -> dict[str, Any]:
        """Get plans, specs, and addenda for a specific project."""
        return await self._get(
            "/api/1.0/int/project/document/search",
            params={"projectId": project_id},
        )

    # ------------------------------------------------------------------
    # Spec Alert endpoints
    # ------------------------------------------------------------------

    async def get_spec_alert_names(self) -> dict[str, Any]:
        """Get all available spec alert names."""
        return await self._get("/api/1.0/int/spec-alert/names")
