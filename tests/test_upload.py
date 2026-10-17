"""Unit tests for file and directory uploads with preflight validation (T-CLI-02, T-CLI-03)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ubuntu_bio.exceptions import ClientValidationError
from ubuntu_bio.upload import upload_file, upload_folder


def test_upload_file_pipeline(tmp_path: Path) -> None:
    """Test full upload_file sequence: preupload -> LFS batch -> PUT -> commit."""
    sample_file = tmp_path / "isolate_01.fasta"
    sample_file.write_text(">seq1\nATGCGATC\n")

    # Mock responses
    pre_resp = MagicMock()
    pre_resp.status_code = 200
    pre_resp.json.return_value = {
        "repo_slug": "pasteur/lassa",
        "cas_url": "http://localhost:8080",
        "cas_write_token": "mock_cas_jwt_token",
    }

    batch_resp = MagicMock()
    batch_resp.status_code = 200
    batch_resp.json.return_value = {
        "transfer": "basic",
        "objects": [
            {
                "oid": "mock_oid",
                "actions": {
                    "upload": {
                        "href": "http://localhost:8000/api/repos/pasteur/lassa/lfs/mock_oid",
                        "header": {"Authorization": "Bearer mock_cas_jwt_token"},
                    }
                },
            }
        ],
    }

    put_resp = MagicMock()
    put_resp.status_code = 200

    commit_resp = MagicMock()
    commit_resp.status_code = 201
    commit_resp.json.return_value = {"status": "committed", "repo_slug": "pasteur/lassa"}

    with patch("httpx.post") as mock_post, patch("httpx.put", return_value=put_resp):
        mock_post.side_effect = [pre_resp, batch_resp, commit_resp]
        res = upload_file(
            repo_id="pasteur/lassa",
            path_or_bytes=sample_file,
            path_in_repo="assemblies/isolate_01.fasta",
            token="ubp_test_token",
        )
        assert res["status"] == "committed"
        assert mock_post.call_count == 3


def test_upload_folder_preflight_blocks_human_data_readme(tmp_path: Path) -> None:
    """Ensure preflight check blocks folders containing human Taxon ID 9606 in README.md."""
    folder = tmp_path / "bad_dataset"
    folder.mkdir()

    readme_content = """---
title: "Human African genomics"
domain: "bacteria"
access: "public"
license: "cc-by-4.0"
taxon_ids: [9606]
---
# Banned Human Dataset
"""
    (folder / "README.md").write_text(readme_content)

    with pytest.raises(ClientValidationError, match=r"Human genomic data .* is prohibited"):
        upload_folder(
            repo_id="pasteur/human-study",
            folder_path=folder,
            token="ubp_test_token",
        )


def test_upload_folder_preflight_blocks_human_data_samples(tmp_path: Path) -> None:
    """Ensure preflight check blocks folders containing human Taxon ID 9606 in samples.tsv."""
    folder = tmp_path / "bad_samples"
    folder.mkdir()

    samples_content = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\nSMP_001\t9606\tNG\t2023-01-01\n"
    )
    (folder / "samples.tsv").write_text(samples_content)

    with pytest.raises(ClientValidationError, match=r"Human data .* is prohibited"):
        upload_folder(
            repo_id="pasteur/human-samples",
            folder_path=folder,
            token="ubp_test_token",
        )
