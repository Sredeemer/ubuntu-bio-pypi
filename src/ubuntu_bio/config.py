"""Configuration, environment variables, and token storage (M2-02)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HUB_URL = os.environ.get("UBUNTUBIO_HUB_URL", "https://ubuntu-bio-web.vercel.app")
DEFAULT_CONFIG_DIR = Path(
    os.environ.get("UBUNTUBIO_CONFIG_DIR", Path.home() / ".config" / "ubuntubio")
)
DEFAULT_CACHE_DIR = Path(
    os.environ.get("UBUNTUBIO_CACHE_DIR", Path.home() / ".cache" / "ubuntubio")
)
TOKEN_FILENAME = "token"


def get_config_dir() -> Path:
    """Return path to config directory, creating it with 0700 permissions if needed."""
    config_dir = DEFAULT_CONFIG_DIR
    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    return config_dir


def get_cache_dir() -> Path:
    """Return path to cache directory, creating it if needed."""
    cache_dir = DEFAULT_CACHE_DIR
    if not cache_dir.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_token_path(custom_path: Path | None = None) -> Path:
    """Return path to the token file."""
    if custom_path:
        return custom_path
    return get_config_dir() / TOKEN_FILENAME


def save_token(token: str, custom_path: Path | None = None) -> Path:
    """Save token to disk with strict 0600 file permissions."""
    token_path = get_token_path(custom_path)
    token_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)

    # Write token with 0600 permissions
    clean_token = token.strip()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    fd = os.open(token_path, flags, mode)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(clean_token)

    return token_path


def get_token(custom_path: Path | None = None) -> str | None:
    """Read saved authentication token from environment variable or token file."""
    # Environment variable takes precedence
    env_token = os.environ.get("UBUNTUBIO_TOKEN")
    if env_token:
        return env_token.strip()

    token_path = get_token_path(custom_path)
    if token_path.exists():
        try:
            return token_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return None


def delete_token(custom_path: Path | None = None) -> bool:
    """Delete saved token file."""
    token_path = get_token_path(custom_path)
    if token_path.exists():
        token_path.unlink()
        return True
    return False


def get_hub_url() -> str:
    """Return the base URL of the UbuntuBio Hub API."""
    return os.environ.get("UBUNTUBIO_HUB_URL", DEFAULT_HUB_URL).rstrip("/")
