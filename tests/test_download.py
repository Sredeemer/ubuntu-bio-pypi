"""Unit tests for file, snapshot, and remote_files downloads (T-CLI-04..07)."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ubuntu_bio.download import download_file, download_remote_files, snapshot_download
from ubuntu_bio.exceptions import DownloadError


def test_download_file_caching(tmp_path: Path) -> None:
    """Test file download caching and atomic writes."""
    cache_dir = tmp_path / "cache"
    fake_content = b">isolate_01\nATGCGATC\n"

    # Mock response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_bytes.return_value = [fake_content]

    with patch("httpx.stream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = mock_resp

        # First call downloads and writes to cache
        file_path = download_file(
            repo_id="pasteur/lassa",
            filename="assemblies/isolate_01.fasta",
            cache_dir=cache_dir,
            token="ubp_test_token",
        )
        assert file_path.exists()
        assert file_path.read_bytes() == fake_content
        assert mock_stream.call_count == 1

        # Second call hits cache without calling HTTP stream
        cached = download_file(
            repo_id="pasteur/lassa",
            filename="assemblies/isolate_01.fasta",
            cache_dir=cache_dir,
            force_download=False,
        )
        assert cached == file_path
        assert mock_stream.call_count == 1  # Unchanged!


def test_snapshot_download(tmp_path: Path) -> None:
    """Test snapshot_download downloads all files in repository tree."""
    out_dir = tmp_path / "snapshot_out"
    cache_dir = tmp_path / "cache"

    tree_data = {
        "ref": "main",
        "items": [
            {"type": "blob", "path": "README.md"},
            {"type": "blob", "path": "samples.tsv"},
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_bytes.return_value = [b"mock content"]

    with (
        patch("ubuntu_bio.download.get_tree", return_value=tree_data),
        patch("httpx.stream") as mock_stream,
    ):
        mock_stream.return_value.__enter__.return_value = mock_resp

        target = snapshot_download(
            repo_id="pasteur/lassa",
            output_dir=out_dir,
            cache_dir=cache_dir,
        )
        assert target == out_dir
        assert (out_dir / "README.md").exists()
        assert (out_dir / "samples.tsv").exists()


def test_download_remote_files_md5_verification(tmp_path: Path) -> None:
    """Test download_remote_files verifies MD5 checksums and sizes."""
    out_dir = tmp_path / "remote_out"
    content = b"FASTA_GENOME_DATA_HERE"
    valid_md5 = hashlib.md5(content).hexdigest()
    valid_size = len(content)

    tsv_file = tmp_path / "remote_files.tsv"
    tsv_content = (
        "filename\turl\tmd5\tsize_bytes\n"
        f"isolate_01.fa\thttps://data.pasteur.sn/isolate_01.fa\t{valid_md5}\t{valid_size}\n"
    )
    tsv_file.write_text(tsv_content)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_bytes.return_value = [content]

    with patch("httpx.stream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = mock_resp

        files = download_remote_files(tsv_path=tsv_file, output_dir=out_dir)
        assert len(files) == 1
        assert files[0].exists()
        assert files[0].name == "isolate_01.fa"
        assert files[0].read_bytes() == content


def test_download_remote_files_md5_mismatch_raises(tmp_path: Path) -> None:
    """Test download_remote_files raises DownloadError on corrupted/tampered data."""
    out_dir = tmp_path / "remote_out"
    content = b"TAMPERED_DATA"
    wrong_md5 = "00000000000000000000000000000000"
    wrong_size = len(content)

    tsv_file = tmp_path / "remote_files.tsv"
    tsv_content = (
        "filename\turl\tmd5\tsize_bytes\n"
        f"corrupt.fa\thttps://data.pasteur.sn/corrupt.fa\t{wrong_md5}\t{wrong_size}\n"
    )
    tsv_file.write_text(tsv_content)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_bytes.return_value = [content]

    with patch("httpx.stream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = mock_resp
        with pytest.raises(DownloadError, match="MD5 mismatch"):
            download_remote_files(tsv_path=tsv_file, output_dir=out_dir, max_retries=1)
