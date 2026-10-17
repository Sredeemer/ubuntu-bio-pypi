"""Unit tests for repository search functionality."""

from unittest.mock import MagicMock, patch

from ubuntu_bio.search import search


def test_search_endpoint_success() -> None:
    """Ensure search queries the hub search endpoint when available."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"slug": "pasteur/lassa-virus", "domain": "virus", "access": "public"}
    ]

    with patch("httpx.get", return_value=mock_resp) as mock_get:
        results = search("lassa", domain="virus", token="ubp_test_token")
        assert len(results) == 1
        assert results[0]["slug"] == "pasteur/lassa-virus"
        assert mock_get.called


def test_search_fallback_to_list_repos() -> None:
    """Ensure search falls back to keyword matching over list_repos if search endpoint fails."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    repos_data = [
        {
            "slug": "kemer/vibrio-cholerae",
            "name": "vibrio-cholerae",
            "description": "Cholera isolates from Lake Victoria",
            "domain": "bacteria",
        },
        {
            "slug": "pasteur/yellow-fever",
            "name": "yellow-fever",
            "description": "Vector surveillance data",
            "domain": "virus",
        },
    ]

    with (
        patch("httpx.get", return_value=mock_resp),
        patch("ubuntu_bio.search.list_repos", return_value=repos_data),
    ):
        results = search("cholera", domain="bacteria")
        assert len(results) == 1
        assert results[0]["slug"] == "kemer/vibrio-cholerae"
