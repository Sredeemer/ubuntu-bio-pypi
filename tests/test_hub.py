"""Unit tests for repository metadata and inspect client (M2-03)."""

from unittest.mock import MagicMock, patch

import pytest

from ubuntu_bio.exceptions import (
    RepositoryNotFoundError,
)
from ubuntu_bio.hub import create_repo, get_commits, get_repo, get_tree, list_repos


def test_create_repo_success() -> None:
    """Test successful repository creation."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "slug": "kfri/sleeping-sickness-2024",
        "domain": "parasite",
        "access": "public",
    }

    with patch("httpx.post", return_value=mock_resp):
        repo = create_repo(
            repo_id="kfri/sleeping-sickness-2024",
            domain="parasite",
            token="ubp_test_token",
        )
        assert repo["slug"] == "kfri/sleeping-sickness-2024"
        assert repo["domain"] == "parasite"


def test_create_repo_conflict_exist_ok() -> None:
    """Test create_repo with exist_ok=True on 409 conflict."""
    post_resp = MagicMock()
    post_resp.status_code = 409

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = {"slug": "kfri/sleeping-sickness-2024"}

    with patch("httpx.post", return_value=post_resp), patch("httpx.get", return_value=get_resp):
        repo = create_repo(
            repo_id="kfri/sleeping-sickness-2024",
            domain="parasite",
            exist_ok=True,
            token="ubp_test_token",
        )
        assert repo["slug"] == "kfri/sleeping-sickness-2024"


def test_get_repo_not_found() -> None:
    """Test get_repo raises RepositoryNotFoundError on 404."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.get", return_value=mock_resp):
        with pytest.raises(RepositoryNotFoundError, match="not found"):
            get_repo("kfri/nonexistent-repo")


def test_list_repos() -> None:
    """Test list_repos retrieves array of repositories."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"slug": "pasteur/lassa", "domain": "virus"},
        {"slug": "cphi/cholera", "domain": "bacteria"},
    ]

    with patch("httpx.get", return_value=mock_resp):
        repos = list_repos()
        assert len(repos) == 2
        assert repos[0]["slug"] == "pasteur/lassa"


def test_get_tree_and_commits() -> None:
    """Test get_tree and get_commits endpoints."""
    tree_resp = MagicMock()
    tree_resp.status_code = 200
    tree_resp.json.return_value = {
        "ref": "main",
        "items": [{"mode": "100644", "type": "blob", "path": "README.md", "size": 100}],
    }

    commits_resp = MagicMock()
    commits_resp.status_code = 200
    commits_resp.json.return_value = [
        {"commit_hash": "a1b2c3d4", "author": "Researcher", "message": "Initial commit"}
    ]

    with patch("httpx.get") as mock_get:
        mock_get.side_effect = [tree_resp, commits_resp]
        tree = get_tree("pasteur/lassa")
        assert len(tree["items"]) == 1
        assert tree["items"][0]["path"] == "README.md"

        commits = get_commits("pasteur/lassa")
        assert len(commits) == 1
        assert commits[0]["commit_hash"] == "a1b2c3d4"
