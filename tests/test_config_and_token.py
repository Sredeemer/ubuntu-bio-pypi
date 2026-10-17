"""Unit tests for config and 0600 token storage (T-CLI-01)."""

import stat
from pathlib import Path

import pytest

from ubuntu_bio.config import delete_token, get_token, save_token


def test_token_storage_permissions_and_lifecycle(tmp_path: Path) -> None:
    """Ensure tokens are stored with strict 0600 permissions."""
    custom_token_file = tmp_path / "custom_config" / "token"

    # Save token
    test_token = "ubp_test_token_secret_12345"
    saved_path = save_token(test_token, custom_path=custom_token_file)
    assert saved_path == custom_token_file
    assert saved_path.exists()

    # Check file permissions are 0600 (owner read/write only)
    mode = stat.S_IMODE(saved_path.stat().st_mode)
    assert mode == 0o600

    # Retrieve token
    retrieved = get_token(custom_path=custom_token_file)
    assert retrieved == test_token

    # Delete token
    assert delete_token(custom_path=custom_token_file)
    assert not saved_path.exists()
    assert get_token(custom_path=custom_token_file) is None


def test_environment_variable_token_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure UBUNTUBIO_TOKEN environment variable overrides disk token."""
    custom_token_file = tmp_path / "token"
    save_token("ubp_disk_token", custom_path=custom_token_file)

    monkeypatch.setenv("UBUNTUBIO_TOKEN", "ubp_env_token")
    assert get_token(custom_path=custom_token_file) == "ubp_env_token"
