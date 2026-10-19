"""UbuntuBio Python Client Library (ubuntu-bio).

African Bioinformatics Data Hub client for discovering, downloading,
publishing, and versioning genomic datasets.
"""

from __future__ import annotations

from ubuntu_bio.auth import login, logout, poll_device_token, request_device_code, whoami
from ubuntu_bio.config import get_cache_dir, get_config_dir, get_hub_url
from ubuntu_bio.download import download_file, download_remote_files, snapshot_download
from ubuntu_bio.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ClientValidationError,
    DownloadError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    UbuntuBioError,
    UploadError,
)
from ubuntu_bio.hub import create_repo, get_commits, get_repo, get_tree, list_repos
from ubuntu_bio.search import search
from ubuntu_bio.upload import upload_file, upload_folder

__version__ = "0.1.0"

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ClientValidationError",
    "DownloadError",
    "RepositoryAlreadyExistsError",
    "RepositoryNotFoundError",
    "UbuntuBioError",
    "UploadError",
    "create_repo",
    "download_file",
    "download_remote_files",
    "get_cache_dir",
    "get_commits",
    "get_config_dir",
    "get_hub_url",
    "get_repo",
    "get_tree",
    "list_repos",
    "login",
    "logout",
    "poll_device_token",
    "request_device_code",
    "search",
    "snapshot_download",
    "upload_file",
    "upload_folder",
    "whoami",
]
