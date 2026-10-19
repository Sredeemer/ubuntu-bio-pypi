"""Unit tests for authentication and session management (M2-02)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ubuntu_bio.auth import login, logout, whoami
from ubuntu_bio.config import get_token
from ubuntu_bio.exceptions import AuthenticationError


def test_whoami_success(tmp_path: Path) -> None:
    """Test whoami retrieves profile with valid token."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "user-uuid-123",
        "name": "Dr. Amina Diallo",
        "orcid_id": "0000-0002-1825-0097",
        "email": "amina@pasteur.sn",
    }

    with patch("httpx.get", return_value=mock_resp):
        profile = whoami(token="ubp_valid_token")
        assert profile["name"] == "Dr. Amina Diallo"
        assert profile["orcid_id"] == "0000-0002-1825-0097"


def test_whoami_unauthorized() -> None:
    """Test whoami raises AuthenticationError on 401."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("httpx.get", return_value=mock_resp):
        with pytest.raises(AuthenticationError, match="Invalid or expired"):
            whoami(token="ubp_bad_token")


def test_login_and_logout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test login saves token and logout removes it."""
    test_token_path = tmp_path / "token"
    monkeypatch.setattr("ubuntu_bio.config.get_token_path", lambda custom=None: test_token_path)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "user-uuid-123",
        "name": "Dr. Amina Diallo",
        "orcid_id": "0000-0002-1825-0097",
    }

    with patch("httpx.get", return_value=mock_resp):
        profile = login(token="ubp_saved_token")
        assert profile["name"] == "Dr. Amina Diallo"
        assert get_token(custom_path=test_token_path) == "ubp_saved_token"

        assert logout() is True
        assert get_token(custom_path=test_token_path) is None


def test_find_free_port() -> None:
    """Test finding an available port on loopback."""
    from ubuntu_bio.auth import find_free_port

    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536


def test_loopback_callback_server_flow() -> None:
    """Test LoopbackCallbackServer handles callback request and captures token."""
    import httpx

    from ubuntu_bio.auth import LoopbackCallbackServer, find_free_port

    port = find_free_port()
    server = LoopbackCallbackServer(port=port)
    server.start()

    try:
        # Send HTTP GET callback
        resp = httpx.get(f"http://127.0.0.1:{port}/callback?token=ubp_loopback_test_token")
        assert resp.status_code == 200
        assert "Terminal Authorized!" in resp.text
        assert server.token == "ubp_loopback_test_token"
    finally:
        server.shutdown()


def test_wait_for_auth_token_loopback_immediate() -> None:
    """Test wait_for_auth_token returns token when loopback server has received it."""
    from ubuntu_bio.auth import LoopbackCallbackServer, wait_for_auth_token

    mock_server = LoopbackCallbackServer(port=12345)
    mock_server.token = "ubp_instant_token"

    token = wait_for_auth_token(loopback_server=mock_server, timeout=5)
    assert token == "ubp_instant_token"


def test_wait_for_auth_token_device_fallback() -> None:
    """Test wait_for_auth_token falls back to device code polling."""
    from unittest.mock import MagicMock, patch

    from ubuntu_bio.auth import wait_for_auth_token

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "ubp_device_fallback_token"}

    with patch("httpx.post", return_value=mock_resp):
        token = wait_for_auth_token(
            loopback_server=None,
            device_code="dev_code_123",
            interval=0,
            timeout=5,
        )
        assert token == "ubp_device_fallback_token"
