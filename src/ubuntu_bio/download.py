"""File, snapshot, and remote_files.tsv download coordination (M2-04, M2-05)."""

from __future__ import annotations

import csv
import hashlib
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from ubuntu_bio.config import get_cache_dir, get_hub_url, get_token
from ubuntu_bio.exceptions import (
    AuthenticationError,
    DownloadError,
    RepositoryNotFoundError,
    UbuntuBioError,
)
from ubuntu_bio.hub import _split_repo_id, get_tree


def _calculate_md5(file_path: Path) -> str:
    """Calculate MD5 checksum of a file."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_file(
    repo_id: str,
    filename: str,
    revision: str = "main",
    output_path: str | Path | None = None,
    cache_dir: Path | None = None,
    force_download: bool = False,
    token: str | None = None,
    hub_url: str | None = None,
) -> Path:
    """Download a single file from a repository, using local caching."""
    owner, name = _split_repo_id(repo_id)
    base_url = (hub_url or get_hub_url()).rstrip("/")
    active_token = token or get_token()

    clean_file = filename.strip("/")
    base_cache = cache_dir or get_cache_dir()
    cached_file = base_cache / owner / name / revision / clean_file

    if cached_file.exists() and not force_download:
        if output_path:
            dest = Path(output_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_file, dest)
            return dest
        return cached_file

    headers = {}
    if active_token:
        headers["Authorization"] = f"Bearer {active_token}"

    download_url = f"{base_url}/api/repos/{owner}/{name}/raw/{revision}/{clean_file}"

    cached_file.parent.mkdir(parents=True, exist_ok=True)
    temp_target = cached_file.with_suffix(".tmp")

    try:
        with httpx.stream("GET", download_url, headers=headers, timeout=60.0) as resp:
            if resp.status_code == 404:
                raise RepositoryNotFoundError(
                    f"File '{clean_file}' or repository '{repo_id}' not found."
                )
            if resp.status_code == 401:
                raise AuthenticationError("Authentication required to download this file.")
            if resp.status_code != 200:
                err_msg = resp.read().decode("utf-8", errors="replace")
                raise DownloadError(f"Download failed (status {resp.status_code}): {err_msg}")

            with open(temp_target, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
    except httpx.RequestError as exc:
        if temp_target.exists():
            temp_target.unlink()
        raise DownloadError(f"Connection error downloading '{clean_file}': {exc}") from exc

    # Atomic move to final cache destination
    temp_target.replace(cached_file)

    if output_path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached_file, dest)
        return dest

    return cached_file


def snapshot_download(
    repo_id: str,
    revision: str = "main",
    output_dir: str | Path | None = None,
    cache_dir: Path | None = None,
    force_download: bool = False,
    token: str | None = None,
    hub_url: str | None = None,
) -> Path:
    """Download the full directory snapshot of a repository at a given revision."""
    owner, name = _split_repo_id(repo_id)
    tree_data = get_tree(repo_id=repo_id, revision=revision, token=token, hub_url=hub_url)
    items: list[dict[str, Any]] = tree_data.get("items", [])

    base_dir = cache_dir or get_cache_dir()
    target_dir = Path(output_dir) if output_dir else base_dir / owner / name / revision
    target_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        # We only download blobs (files), trees represent directories
        if item.get("type") == "blob":
            file_rel_path = item["path"]
            download_file(
                repo_id=repo_id,
                filename=file_rel_path,
                revision=revision,
                output_path=target_dir / file_rel_path,
                cache_dir=cache_dir,
                force_download=force_download,
                token=token,
                hub_url=hub_url,
            )

    return target_dir


def download_remote_files(
    tsv_path: str | Path,
    output_dir: str | Path,
    max_retries: int = 3,
) -> list[Path]:
    """Download external files listed in remote_files.tsv with MD5 checksum verification."""
    path = Path(tsv_path)
    if not path.is_file():
        raise FileNotFoundError(f"remote_files.tsv not found at '{tsv_path}'.")

    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files: list[Path] = []

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        expected_cols = {"filename", "url", "md5", "size_bytes"}
        if not reader.fieldnames or not expected_cols.issubset(set(reader.fieldnames)):
            raise UbuntuBioError(
                f"remote_files.tsv must contain mandatory columns: {sorted(expected_cols)}"
            )

        for row in reader:
            filename = row["filename"].strip()
            url = row["url"].strip()
            expected_md5 = row["md5"].strip().lower()
            expected_size = int(row["size_bytes"].strip())

            target_file = dest_dir / filename
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # Check if file already exists with matching MD5
            if target_file.exists():
                computed_md5 = _calculate_md5(target_file)
                if computed_md5.lower() == expected_md5:
                    downloaded_files.append(target_file)
                    continue

            # Download with retries
            success = False
            last_err: Exception | None = None

            for attempt in range(1, max_retries + 1):
                temp_file = target_file.with_suffix(".tmp")
                try:
                    with httpx.stream("GET", url, timeout=60.0, follow_redirects=True) as resp:
                        if resp.status_code != 200:
                            raise DownloadError(f"HTTP {resp.status_code} downloading {url}")
                        with open(temp_file, "wb") as out_f:
                            for chunk in resp.iter_bytes():
                                out_f.write(chunk)

                    # Verify MD5 checksum
                    computed = _calculate_md5(temp_file)
                    if computed.lower() != expected_md5:
                        temp_file.unlink()
                        raise DownloadError(
                            f"MD5 mismatch for {filename}: expected {expected_md5}, got {computed}"
                        )

                    # Verify file size
                    if temp_file.stat().st_size != expected_size:
                        actual_size = temp_file.stat().st_size
                        temp_file.unlink()
                        raise DownloadError(
                            f"Size mismatch for {filename}: "
                            f"expected {expected_size}, got {actual_size}"
                        )

                    temp_file.replace(target_file)
                    downloaded_files.append(target_file)
                    success = True
                    break
                except Exception as exc:
                    last_err = exc
                    if temp_file.exists():
                        temp_file.unlink()
                    time.sleep(0.5 * attempt)

            if not success:
                raise DownloadError(
                    f"Failed to download remote file '{filename}' from '{url}' "
                    f"after {max_retries} attempts: {last_err}"
                )

    return downloaded_files
