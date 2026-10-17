"""Authentication and session management for UbuntuBio client (M2-02)."""

from __future__ import annotations

from typing import Any

import httpx

from ubuntu_bio.config import delete_token, get_hub_url, get_token, save_token
from ubuntu_bio.exceptions import AuthenticationError


def whoami(
    token: str | None = None,
    hub_url: str | None = None,
) -> dict[str, Any]:
    """Retrieve profile of currently authenticated user."""
    active_token = token or get_token()
    if not active_token:
        raise AuthenticationError(
            "No authentication token found. Please run 'ubio login' or provide token."
        )

    base_url = (hub_url or get_hub_url()).rstrip("/")
    headers = {"Authorization": f"Bearer {active_token}"}

    try:
        resp = httpx.get(f"{base_url}/api/auth/whoami", headers=headers, timeout=15.0)
    except httpx.RequestError as exc:
        raise AuthenticationError(f"Failed to connect to UbuntuBio Hub: {exc}") from exc

    if resp.status_code == 401:
        raise AuthenticationError("Invalid or expired authentication token.")
    if resp.status_code != 200:
        raise AuthenticationError(
            f"Failed to verify authentication (status {resp.status_code}): {resp.text}"
        )

    data: dict[str, Any] = resp.json()
    return data


def login(
    token: str,
    hub_url: str | None = None,
) -> dict[str, Any]:
    """Verify personal access token and persist locally to ~/.config/ubuntubio/token."""
    clean_token = token.strip()
    profile = whoami(token=clean_token, hub_url=hub_url)
    save_token(clean_token)
    return profile


def logout() -> bool:
    """Delete local authentication token."""
    return delete_token()
