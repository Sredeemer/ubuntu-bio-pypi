"""File and directory upload coordination for UbuntuBio Hub (M2-03)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import yaml

from ubuntu_bio.config import get_hub_url, get_token
from ubuntu_bio.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ClientValidationError,
    RepositoryNotFoundError,
    UploadError,
)
from ubuntu_bio.hub import _split_repo_id

DEFAULT_IGNORE_PATTERNS = {
    ".git",
    ".github",
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    ".env",
}


def _calculate_sha256(data: bytes) -> str:
    """Calculate hex-encoded SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def _validate_local_metadata(folder_path: Path) -> None:
    """Perform preflight checks on README.md and samples.tsv before uploading."""
    readme_path = folder_path / "README.md"
    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ClientValidationError(
                "Local README.md must begin with '---' YAML front-matter boundary."
            )
        # Parse YAML frontmatter
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx == -1:
            raise ClientValidationError(
                "Local README.md has unterminated YAML front-matter; missing closing '---'."
            )
        try:
            frontmatter = yaml.safe_load("\n".join(lines[1:end_idx]))
            if not isinstance(frontmatter, dict):
                raise ClientValidationError(
                    "YAML front-matter in README.md must be a key-value mapping."
                )
            # Enforce non-human rule
            taxa = frontmatter.get("taxa") or []
            taxon_ids = frontmatter.get("taxon_ids") or []
            all_taxa = list(taxon_ids)
            for t in taxa:
                if isinstance(t, dict) and "ncbi_taxon_id" in t:
                    all_taxa.append(t["ncbi_taxon_id"])
            if 9606 in all_taxa:
                raise ClientValidationError(
                    "Upload rejected: Human genomic data (Taxon ID 9606) is prohibited in v1."
                )
        except yaml.YAMLError as exc:
            raise ClientValidationError(f"Invalid YAML syntax in README.md: {exc}") from exc

    samples_path = folder_path / "samples.tsv"
    if samples_path.exists():
        samples_text = samples_path.read_text(encoding="utf-8")
        s_lines = [ln.strip() for ln in samples_text.splitlines() if ln.strip()]
        if not s_lines:
            raise ClientValidationError("Local samples.tsv is empty.")
        header = s_lines[0].split("\t")
        if "sample_id" not in header:
            raise ClientValidationError("samples.tsv is missing mandatory 'sample_id' column.")
        # Check taxon_id column if present
        if "taxon_id" in header:
            t_idx = header.index("taxon_id")
            for r_idx, row in enumerate(s_lines[1:], start=2):
                cols = row.split("\t")
                if len(cols) > t_idx and cols[t_idx].strip() == "9606":
                    raise ClientValidationError(
                        f"samples.tsv row {r_idx}: Human data (Taxon ID 9606) is prohibited in v1."
                    )


def upload_file(
    repo_id: str,
    path_or_bytes: str | Path | bytes,
    path_in_repo: str,
    branch: str = "main",
    message: str | None = None,
    token: str | None = None,
    hub_url: str | None = None,
) -> dict[str, Any]:
    """Upload a single file to a repository and commit it."""
    owner, name = _split_repo_id(repo_id)
    base_url = (hub_url or get_hub_url()).rstrip("/")
    active_token = token or get_token()

    if not active_token:
        raise AuthenticationError("Authentication required to upload files.")

    headers = {"Authorization": f"Bearer {active_token}"}

    # Resolve payload bytes
    if isinstance(path_or_bytes, bytes):
        content = path_or_bytes
    else:
        p = Path(path_or_bytes)
        if not p.is_file():
            raise FileNotFoundError(f"Local file '{path_or_bytes}' not found.")
        content = p.read_bytes()

    sha256 = _calculate_sha256(content)
    size_bytes = len(content)
    clean_path = path_in_repo.strip("/")

    # 1. Preupload inquiry
    try:
        pre_resp = httpx.post(
            f"{base_url}/api/repos/{owner}/{name}/preupload",
            json={"filenames": [clean_path]},
            headers=headers,
            timeout=20.0,
        )
    except httpx.RequestError as exc:
        raise UploadError(f"Connection error during preupload inquiry: {exc}") from exc

    if pre_resp.status_code == 404:
        raise RepositoryNotFoundError(f"Repository '{repo_id}' not found.")
    if pre_resp.status_code == 403:
        raise AuthorizationError(f"Write permission denied on repository '{repo_id}'.")
    if pre_resp.status_code != 200:
        raise UploadError(
            f"Preupload inquiry failed (status {pre_resp.status_code}): {pre_resp.text}"
        )

    pre_data = pre_resp.json()
    cas_token = pre_data["cas_write_token"]

    # 2. Negotiate Git LFS Batch Upload
    lfs_req = {
        "operation": "upload",
        "transfers": ["basic"],
        "objects": [{"oid": sha256, "size": size_bytes}],
    }
    try:
        batch_resp = httpx.post(
            f"{base_url}/{owner}/{name}.git/info/lfs/objects/batch",
            json=lfs_req,
            headers=headers,
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise UploadError(f"Connection error during LFS batch negotiation: {exc}") from exc

    if batch_resp.status_code != 200:
        raise UploadError(
            f"LFS batch negotiation failed (status {batch_resp.status_code}): {batch_resp.text}"
        )

    batch_data = batch_resp.json()
    obj_data = batch_data["objects"][0]
    upload_action = obj_data["actions"]["upload"]
    upload_url = upload_action["href"]
    upload_headers = upload_action.get("header", {})
    if "Authorization" not in upload_headers:
        upload_headers["Authorization"] = f"Bearer {cas_token}"

    # 3. Stream/PUT file content
    try:
        put_resp = httpx.put(
            upload_url,
            content=content,
            headers=upload_headers,
            timeout=60.0,
        )
    except httpx.RequestError as exc:
        raise UploadError(f"Connection error transferring object payload: {exc}") from exc

    if put_resp.status_code not in (200, 201):
        raise UploadError(
            f"Object upload transfer failed (status {put_resp.status_code}): {put_resp.text}"
        )

    # 4. Finalize commit on hub
    commit_payload = {
        "branch": branch,
        "message": message or f"Upload {clean_path}",
        "files": [
            {
                "path": clean_path,
                "sha256": sha256,
                "xet_hash": sha256,
                "size_bytes": size_bytes,
            }
        ],
    }

    try:
        commit_resp = httpx.post(
            f"{base_url}/api/repos/{owner}/{name}/commit",
            json=commit_payload,
            headers=headers,
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise UploadError(f"Connection error registering commit: {exc}") from exc

    if commit_resp.status_code != 201:
        raise UploadError(
            f"Commit registration failed (status {commit_resp.status_code}): {commit_resp.text}"
        )

    res: dict[str, Any] = commit_resp.json()
    return res


def upload_folder(
    repo_id: str,
    folder_path: str | Path,
    branch: str = "main",
    message: str | None = None,
    token: str | None = None,
    hub_url: str | None = None,
    ignore_patterns: set[str] | None = None,
) -> dict[str, Any]:
    """Upload an entire directory of files with preflight schema validation."""
    root_folder = Path(folder_path)
    if not root_folder.is_dir():
        raise NotADirectoryError(f"Specified path '{folder_path}' is not a directory.")

    # 1. Run local preflight metadata checks
    _validate_local_metadata(root_folder)

    ignored = DEFAULT_IGNORE_PATTERNS | (ignore_patterns or set())
    files_to_upload: list[tuple[Path, str]] = []

    for path in root_folder.rglob("*"):
        if path.is_file():
            # Check ignore patterns
            rel_parts = set(path.relative_to(root_folder).parts)
            if rel_parts & ignored:
                continue
            rel_path = str(path.relative_to(root_folder))
            files_to_upload.append((path, rel_path))

    if not files_to_upload:
        raise UploadError(f"No files found in '{folder_path}' to upload.")

    committed_files: list[str] = []
    # Upload each file
    for local_file, repo_rel_path in files_to_upload:
        upload_file(
            repo_id=repo_id,
            path_or_bytes=local_file,
            path_in_repo=repo_rel_path,
            branch=branch,
            message=message or f"Upload folder {root_folder.name}",
            token=token,
            hub_url=hub_url,
        )
        committed_files.append(repo_rel_path)

    return {
        "status": "committed",
        "repo_slug": repo_id,
        "branch": branch,
        "files_count": len(committed_files),
        "files": committed_files,
    }
