"""Repository metadata and management client for UbuntuBio Hub (M2-03)."""

from __future__ import annotations

from typing import Any

import httpx

from ubuntu_bio.config import get_hub_url, get_token
from ubuntu_bio.exceptions import (
    AuthenticationError,
    AuthorizationError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    UbuntuBioError,
)


def _split_repo_id(repo_id: str) -> tuple[str, str]:
    """Split 'owner/name' into owner slug and repository name."""
    clean = repo_id.strip().strip("/")
    if "/" not in clean:
        raise ValueError(f"Invalid repository ID '{repo_id}'. Format must be 'owner/repo-name'.")
    owner, name = clean.split("/", 1)
    return owner, name.removesuffix(".git")


def _get_headers(token: str | None = None) -> dict[str, str]:
    """Construct HTTP headers with Bearer authentication if available."""
    active_token = token or get_token()
    headers = {"Accept": "application/json"}
    if active_token:
        headers["Authorization"] = f"Bearer {active_token}"
    return headers


def create_repo(
    repo_id: str,
    domain: str,
    access: str = "public",
    description: str | None = None,
    license: str = "cc-by-4.0",
    exist_ok: bool = False,
    token: str | None = None,
    hub_url: str | None = None,
) -> dict[str, Any]:
    """Create a new dataset repository on UbuntuBio Hub."""
    owner, name = _split_repo_id(repo_id)
    base_url = (hub_url or get_hub_url()).rstrip("/")
    headers = _get_headers(token)

    if "Authorization" not in headers:
        raise AuthenticationError("Authentication required to create a repository.")

    payload = {
        "owner_slug": owner,
        "name": name,
        "domain": domain,
        "access": access,
        "description": description,
        "license": license,
    }

    try:
        resp = httpx.post(f"{base_url}/api/repos", json=payload, headers=headers, timeout=20.0)
    except httpx.RequestError as exc:
        raise UbuntuBioError(f"Connection error creating repository: {exc}") from exc

    if resp.status_code == 409:
        if exist_ok:
            return get_repo(repo_id=repo_id, token=token, hub_url=hub_url)
        raise RepositoryAlreadyExistsError(f"Repository '{repo_id}' already exists.")
    if resp.status_code == 401:
        raise AuthenticationError("Invalid or expired authentication credentials.")
    if resp.status_code == 403:
        raise AuthorizationError(f"Permission denied creating repository under '{owner}'.")
    if resp.status_code != 201:
        raise UbuntuBioError(
            f"Failed to create repository (status {resp.status_code}): {resp.text}"
        )

    data: dict[str, Any] = resp.json()
    return data


def get_repo(
    repo_id: str,
    token: str | None = None,
    hub_url: str | None = None,
) -> dict[str, Any]:
    """Fetch repository metadata and status."""
    owner, name = _split_repo_id(repo_id)
    base_url = (hub_url or get_hub_url()).rstrip("/")
    headers = _get_headers(token)

    try:
        resp = httpx.get(f"{base_url}/api/repos/{owner}/{name}", headers=headers, timeout=15.0)
    except httpx.RequestError as exc:
        raise UbuntuBioError(f"Connection error fetching repository: {exc}") from exc

    if resp.status_code == 404:
        raise RepositoryNotFoundError(f"Repository '{repo_id}' not found or access restricted.")
    if resp.status_code == 401:
        raise AuthenticationError("Authentication required to access this repository.")
    if resp.status_code != 200:
        raise UbuntuBioError(
            f"Failed to retrieve repository (status {resp.status_code}): {resp.text}"
        )

    data: dict[str, Any] = resp.json()
    return data


def list_repos(
    domain: str | None = None,
    token: str | None = None,
    hub_url: str | None = None,
) -> list[dict[str, Any]]:
    """List accessible repositories matching optional filters."""
    base_url = (hub_url or get_hub_url()).rstrip("/")
    headers = _get_headers(token)
    params = {}
    if domain:
        params["domain"] = domain

    try:
        resp = httpx.get(
            f"{base_url}/api/repos",
            params=params,
            headers=headers,
            timeout=20.0,
        )
    except httpx.RequestError as exc:
        raise UbuntuBioError(f"Connection error listing repositories: {exc}") from exc

    if resp.status_code != 200:
        raise UbuntuBioError(
            f"Failed to list repositories (status {resp.status_code}): {resp.text}"
        )

    data: list[dict[str, Any]] = resp.json()
    return data


def get_tree(
    repo_id: str,
    revision: str = "main",
    token: str | None = None,
    hub_url: str | None = None,
) -> dict[str, Any]:
    """List directory tree contents at a specified revision."""
    owner, name = _split_repo_id(repo_id)
    base_url = (hub_url or get_hub_url()).rstrip("/")
    headers = _get_headers(token)

    try:
        resp = httpx.get(
            f"{base_url}/api/repos/{owner}/{name}/tree/{revision}",
            headers=headers,
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise UbuntuBioError(f"Connection error fetching repository tree: {exc}") from exc

    if resp.status_code == 404:
        raise RepositoryNotFoundError(f"Repository '{repo_id}' or revision '{revision}' not found.")
    if resp.status_code != 200:
        raise UbuntuBioError(
            f"Failed to list repository tree (status {resp.status_code}): {resp.text}"
        )

    data: dict[str, Any] = resp.json()
    return data


def get_commits(
    repo_id: str,
    revision: str = "main",
    limit: int = 20,
    token: str | None = None,
    hub_url: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch commit history log for repository."""
    owner, name = _split_repo_id(repo_id)
    base_url = (hub_url or get_hub_url()).rstrip("/")
    headers = _get_headers(token)

    try:
        resp = httpx.get(
            f"{base_url}/api/repos/{owner}/{name}/commits",
            params={"ref": revision, "limit": limit},
            headers=headers,
            timeout=20.0,
        )
    except httpx.RequestError as exc:
        raise UbuntuBioError(f"Connection error fetching commit log: {exc}") from exc

    if resp.status_code == 404:
        raise RepositoryNotFoundError(f"Repository '{repo_id}' not found.")
    if resp.status_code != 200:
        raise UbuntuBioError(f"Failed to fetch commit log (status {resp.status_code}): {resp.text}")

    data: list[dict[str, Any]] = resp.json()
    return data
