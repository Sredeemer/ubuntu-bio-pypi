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
from ubuntu_bio.scaffold import init_dataset
from ubuntu_bio.search import search
from ubuntu_bio.sniffer import SequenceSniffResult, sniff_sequence_file
from ubuntu_bio.upload import upload_file, upload_folder
from ubuntu_bio.validator import ValidationIssue, ValidationResult, validate_local_dataset

__version__ = "0.1.0"

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ClientValidationError",
    "DownloadError",
    "RepositoryAlreadyExistsError",
    "RepositoryNotFoundError",
    "SequenceSniffResult",
    "UbuntuBioError",
    "UploadError",
    "ValidationIssue",
    "ValidationResult",
    "create_repo",
    "download_file",
    "download_remote_files",
    "get_cache_dir",
    "get_commits",
    "get_config_dir",
    "get_hub_url",
    "get_repo",
    "get_tree",
    "init_dataset",
    "list_repos",
    "login",
    "logout",
    "poll_device_token",
    "request_device_code",
    "search",
    "snapshot_download",
    "sniff_sequence_file",
    "upload_file",
    "upload_folder",
    "validate_local_dataset",
    "whoami",
]
