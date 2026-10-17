"""Typed exceptions for UbuntuBio client library."""

from __future__ import annotations


class UbuntuBioError(Exception):
    """Base exception for all UbuntuBio client errors."""


class AuthenticationError(UbuntuBioError):
    """Raised when authentication credentials are missing, invalid, or expired."""


class RepositoryNotFoundError(UbuntuBioError):
    """Raised when a repository does not exist or caller has no read permission."""


class RepositoryAlreadyExistsError(UbuntuBioError):
    """Raised when attempting to create a repository slug that already exists."""


class AuthorizationError(UbuntuBioError):
    """Raised when caller lacks required permission for an action."""


class ClientValidationError(UbuntuBioError):
    """Raised when metadata or input files fail preflight validation."""


class UploadError(UbuntuBioError):
    """Raised when file upload or commit registration fails."""


class DownloadError(UbuntuBioError):
    """Raised when downloading a file or remote object fails or checksum mismatches."""
