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


def request_device_code(hub_url: str | None = None) -> dict[str, Any]:
    """Initiate an RFC 8628 Device Authorization Grant request with the Hub."""
    base_url = (hub_url or get_hub_url()).rstrip("/")
    try:
        resp = httpx.post(f"{base_url}/api/auth/device/code", timeout=15.0)
    except httpx.RequestError as exc:
        raise AuthenticationError(f"Failed to connect to UbuntuBio Hub: {exc}") from exc

    if resp.status_code != 200:
        raise AuthenticationError(
            f"Failed to request device authorization (status {resp.status_code}): {resp.text}"
        )

    data: dict[str, Any] = resp.json()
    return data


def poll_device_token(
    device_code: str,
    interval: int = 2,
    timeout: int = 600,
    hub_url: str | None = None,
) -> str:
    """Poll the Hub until the researcher approves the device code in the browser."""
    import time

    base_url = (hub_url or get_hub_url()).rstrip("/")
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            raise AuthenticationError(
                "Device authorization timed out. Please run 'ubio login' again."
            )

        try:
            resp = httpx.post(
                f"{base_url}/api/auth/device/token",
                json={"device_code": device_code},
                timeout=15.0,
            )
        except httpx.RequestError as exc:
            raise AuthenticationError(f"Connection lost while waiting for approval: {exc}") from exc

        if resp.status_code == 200:
            token_data = resp.json()
            raw_token: str = token_data["access_token"]
            return raw_token

        try:
            err_detail = resp.json().get("detail", "")
        except Exception:
            err_detail = resp.text

        if err_detail == "authorization_pending":
            time.sleep(interval)
            continue
        elif err_detail == "expired_token":
            raise AuthenticationError(
                "This device code has expired. Please run 'ubio login' again."
            )
        elif err_detail == "access_denied":
            raise AuthenticationError("Authorization request was denied in the browser.")
        else:
            raise AuthenticationError(f"Device authorization failed: {err_detail}")
