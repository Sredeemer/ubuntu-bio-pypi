from __future__ import annotations

import contextlib
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
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


SUCCESS_CALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>UbuntuBio Terminal Authorized</title>
  <style>
    body {
      margin: 0;
      background-color: #0b0f17;
      color: #f3f4f6;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 16px;
      padding: 2.5rem 2rem;
      max-width: 440px;
      text-align: center;
      box-shadow: 0 20px 35px rgba(0,0,0,0.6);
    }
    .icon {
      width: 56px;
      height: 56px;
      margin: 0 auto 1.25rem;
      border-radius: 50%;
      background: rgba(0, 237, 100, 0.12);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #00ed64;
      font-size: 28px;
      border: 1px solid rgba(0, 237, 100, 0.25);
    }
    h1 {
      font-size: 1.4rem;
      font-weight: 700;
      margin: 0 0 0.5rem;
      color: #f9fafb;
    }
    p {
      color: #9ca3af;
      font-size: 0.9rem;
      line-height: 1.5;
      margin: 0 0 1.25rem;
    }
    .tag {
      display: inline-block;
      background: rgba(0, 237, 100, 0.1);
      color: #00ed64;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
      border: 1px solid rgba(0, 237, 100, 0.25);
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✓</div>
    <h1>Terminal Authorized!</h1>
    <p>Your UbuntuBio CLI session has been authenticated successfully.</p>
    <p style="color: #6b7280; font-size: 0.85rem;">
      You can now safely close this browser window and return to your terminal.
    </p>
    <div class="tag">● Sovereign Verified (54 AU States)</div>
  </div>
</body>
</html>
"""


def find_free_port() -> int:
    """Find an available port on 127.0.0.1 for local loopback callback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port: int = s.getsockname()[1]
        return port


class LoopbackCallbackServer:
    """Lightweight ephemeral HTTP server on 127.0.0.1 to receive OAuth tokens."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.token: str | None = None
        self._server: Any = None
        self._thread: Any = None
        self._event: threading.Event | None = None

    def start(self) -> None:
        """Start the loopback server in a daemon background thread."""
        outer = self
        self._event = threading.Event()

        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress default stdlib console logging
                pass

            def do_OPTIONS(self) -> None:
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.end_headers()

            def do_GET(self) -> None:
                self.handle_callback()

            def do_POST(self) -> None:
                self.handle_callback()

            def handle_callback(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                token_val = qs.get("token", [None])[0]

                if token_val:
                    outer.token = token_val.strip()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(SUCCESS_CALLBACK_HTML.encode("utf-8"))
                    if outer._event:
                        outer._event.set()
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b"Missing token parameter in callback.")

        self._server = HTTPServer(("127.0.0.1", self.port), CallbackHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        """Shut down and release the socket."""
        if self._server:
            with contextlib.suppress(Exception):
                self._server.shutdown()
                self._server.server_close()
            self._server = None


def wait_for_auth_token(
    loopback_server: LoopbackCallbackServer | None = None,
    device_code: str | None = None,
    interval: int = 1,
    timeout: int = 300,
    hub_url: str | None = None,
) -> str:
    """Wait for auth token from either local loopback server or Hub device polling.

    Returns as soon as the first method receives a valid token, providing instant
    local loopback speed while maintaining resilient remote/headless fallback.
    """
    base_url = (hub_url or get_hub_url()).rstrip("/")
    start_time = time.time()

    try:
        while True:
            if time.time() - start_time > timeout:
                raise AuthenticationError(
                    "Authentication timed out. Please run 'ubio login' again."
                )

            # 1. Check local loopback server
            if loopback_server and loopback_server.token:
                return loopback_server.token

            # 2. Check RFC 8628 Device Token polling if device_code is provided
            if device_code:
                try:
                    resp = httpx.post(
                        f"{base_url}/api/auth/device/token",
                        json={"device_code": device_code},
                        timeout=5.0,
                    )
                    if resp.status_code == 200:
                        token_data = resp.json()
                        raw_token: str = token_data["access_token"]
                        return raw_token

                    err_detail = ""
                    with contextlib.suppress(Exception):
                        err_detail = resp.json().get("detail", "")

                    if err_detail == "expired_token":
                        raise AuthenticationError("This authorization code has expired.")
                    elif err_detail == "access_denied":
                        raise AuthenticationError(
                            "Authorization request was denied in the browser."
                        )
                except httpx.RequestError:
                    pass  # transient network issue, keep checking

            if loopback_server and loopback_server._event:
                loopback_server._event.wait(timeout=interval)
            else:
                time.sleep(interval)
    finally:
        if loopback_server:
            loopback_server.shutdown()
