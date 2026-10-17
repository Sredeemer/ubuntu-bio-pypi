"""Search client for discovering African bioinformatics datasets (M2-06)."""

from __future__ import annotations

from typing import Any

import httpx

from ubuntu_bio.config import get_hub_url, get_token
from ubuntu_bio.hub import list_repos


def search(
    query: str,
    domain: str | None = None,
    limit: int = 20,
    token: str | None = None,
    hub_url: str | None = None,
) -> list[dict[str, Any]]:
    """Search for repositories matching keywords and biological filters."""
    base_url = (hub_url or get_hub_url()).rstrip("/")
    active_token = token or get_token()
    headers = {"Accept": "application/json"}
    if active_token:
        headers["Authorization"] = f"Bearer {active_token}"

    params: dict[str, str | int] = {"q": query, "limit": limit}
    if domain:
        params["domain"] = domain

    # Attempt dedicated hub search endpoint first
    try:
        resp = httpx.get(
            f"{base_url}/api/search",
            params=params,
            headers=headers,
            timeout=15.0,
        )
        if resp.status_code == 200:
            res: list[dict[str, Any]] = resp.json()
            return res
    except httpx.RequestError:
        pass

    # Fallback to list_repos with client-side query matching
    all_repos = list_repos(domain=domain, token=token, hub_url=hub_url)
    q_lower = query.lower()
    matches: list[dict[str, Any]] = []

    for r in all_repos:
        name = r.get("name", "").lower()
        slug = r.get("slug", "").lower()
        desc = (r.get("description") or "").lower()
        r_domain = (r.get("domain") or "").lower()

        if q_lower in name or q_lower in slug or q_lower in desc or q_lower in r_domain:
            matches.append(r)
            if len(matches) >= limit:
                break

    return matches
