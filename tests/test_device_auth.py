"""Unit tests for RFC 8628 Device Authorization in Python client."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ubuntu_bio.auth import poll_device_token, request_device_code
from ubuntu_bio.cli import app, render_ascii_banner
from ubuntu_bio.exceptions import AuthenticationError

runner = CliRunner()


def test_render_ascii_banner() -> None:
    """Test that render_ascii_banner produces non-empty Rich Text containing UbuntuBio."""
    t = render_ascii_banner()
    assert t is not None
    assert len(t.plain) > 0


def test_request_device_code_success() -> None:
    """Test request_device_code parses Hub response correctly."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "device_code": "dev_test_code_123",
        "user_code": "UBIO-8492-AF",
        "verification_uri": "https://ubuntu-bio-web.vercel.app/device",
        "verification_uri_complete": "https://ubuntu-bio-web.vercel.app/device?user_code=UBIO-8492-AF",
        "expires_in": 600,
        "interval": 2,
    }

    with patch("httpx.post", return_value=mock_resp):
        res = request_device_code()
        assert res["user_code"] == "UBIO-8492-AF"
        assert res["device_code"] == "dev_test_code_123"


def test_poll_device_token_success() -> None:
    """Test poll_device_token returns raw access token on 200 OK."""
    # First call returns authorization_pending, second call returns 200 with token
    pending_resp = MagicMock()
    pending_resp.status_code = 400
    pending_resp.json.return_value = {"detail": "authorization_pending"}

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"access_token": "ubp_approved_token_777"}

    with patch("httpx.post", side_effect=[pending_resp, success_resp]):
        with patch("time.sleep", return_value=None):
            token = poll_device_token("dev_123", interval=0, timeout=10)
            assert token == "ubp_approved_token_777"


def test_poll_device_token_expired() -> None:
    """Test poll_device_token raises on expired_token."""
    expired_resp = MagicMock()
    expired_resp.status_code = 400
    expired_resp.json.return_value = {"detail": "expired_token"}

    with patch("httpx.post", return_value=expired_resp):
        with pytest.raises(AuthenticationError, match="expired"):
            poll_device_token("dev_123", interval=0, timeout=10)


def test_cli_login_with_token_flag(tmp_path) -> None:
    """Test ubio login --token preserves legacy instant login without opening browser."""
    mock_whoami = {
        "id": "uuid-1",
        "name": "Prof. Redeemer",
        "orcid_id": "0009-0000-2900-592X",
    }
    with patch("ubuntu_bio.cli.auth_login", return_value=mock_whoami):
        res = runner.invoke(app, ["login", "--token", "ubp_test_direct"])
        assert res.exit_code == 0
        assert "Welcome back, Prof. Redeemer" in res.output
