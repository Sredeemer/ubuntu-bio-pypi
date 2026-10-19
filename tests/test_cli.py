"""Unit tests for UbuntuBio CLI commands (T-CLI-09)."""

from unittest.mock import patch

from typer.testing import CliRunner

from ubuntu_bio.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """Test ubio --version prints version string."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "UbuntuBio CLI version: 0.1.0" in result.stdout


def test_cli_whoami_success() -> None:
    """Test ubio whoami displays user information."""
    fake_profile = {
        "name": "Dr. Amina Diallo",
        "orcid_id": "0000-0002-1825-0097",
        "id": "uuid-123",
        "email": "amina@pasteur.sn",
    }

    with patch("ubuntu_bio.cli.auth_whoami", return_value=fake_profile):
        result = runner.invoke(app, ["whoami"])
        assert result.exit_code == 0
        assert "Dr. Amina Diallo" in result.stdout
        assert "0000-0002-1825-0097" in result.stdout


def test_cli_whoami_with_username() -> None:
    """Test ubio whoami displays researcher @username handle."""
    fake_profile = {
        "name": "Dr. Amina Diallo",
        "username": "amina-diallo",
        "orcid_id": "0000-0002-1825-0097",
        "id": "uuid-123",
        "email": "amina@pasteur.sn",
    }

    with patch("ubuntu_bio.cli.auth_whoami", return_value=fake_profile):
        result = runner.invoke(app, ["whoami"])
        assert result.exit_code == 0
        assert "@amina-diallo" in result.stdout


def test_cli_create_repo() -> None:
    """Test ubio create command with explicit owner/name."""
    fake_repo = {
        "slug": "nicd/lassa-2024",
        "access": "public",
        "domain": "virus",
    }

    with patch("ubuntu_bio.cli.hub_create_repo", return_value=fake_repo):
        result = runner.invoke(app, ["create", "nicd/lassa-2024", "--domain", "virus"])
        assert result.exit_code == 0
        assert "Created repository: nicd/lassa-2024" in result.stdout


def test_cli_create_bare_slug_auto_prefix() -> None:
    """Test ubio create with bare name automatically defaults to @username/name."""
    fake_profile = {
        "name": "Dr. Amina Diallo",
        "username": "amina-diallo",
        "orcid_id": "0000-0002-1825-0097",
    }
    fake_repo = {
        "slug": "amina-diallo/lassa-2024",
        "access": "public",
        "domain": "virus",
    }

    with (
        patch("ubuntu_bio.cli.auth_whoami", return_value=fake_profile),
        patch("ubuntu_bio.cli.hub_create_repo", return_value=fake_repo) as mock_create,
    ):
        result = runner.invoke(app, ["create", "lassa-2024", "--domain", "virus"])
        assert result.exit_code == 0
        assert "Using personal namespace:" in result.stdout
        assert "@amina-diallo" in result.stdout
        assert "amina-diallo/lassa-2024" in result.stdout
        mock_create.assert_called_once_with(
            repo_id="amina-diallo/lassa-2024",
            domain="virus",
            access="public",
            description=None,
            license="cc-by-4.0",
        )


def test_cli_create_bare_slug_unauthenticated() -> None:
    """Test ubio create with bare name when unauthenticated prompts to login or use owner/name."""
    from ubuntu_bio.exceptions import UbuntuBioError

    with patch("ubuntu_bio.cli.auth_whoami", side_effect=UbuntuBioError("No token")):
        result = runner.invoke(app, ["create", "lassa-2024", "--domain", "virus"])
        assert result.exit_code != 0
        assert "Cannot default to personal namespace" in result.stdout


def test_cli_search() -> None:
    """Test ubio search command."""
    fake_results = [
        {
            "slug": "pasteur/cholera-2024",
            "domain": "bacteria",
            "access": "public",
            "description": "Cholera surveillance",
        }
    ]

    with patch("ubuntu_bio.cli.hub_search", return_value=fake_results):
        result = runner.invoke(app, ["search", "cholera"])
        assert result.exit_code == 0
        assert "pasteur/cholera-2024" in result.stdout
