"""Unit tests for dataset scaffolding, local validation, and ubio init/check CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ubuntu_bio.cli import app
from ubuntu_bio.exceptions import ClientValidationError
from ubuntu_bio.scaffold import (
    generate_readme_template,
    generate_remote_files_template,
    generate_samples_tsv_template,
    init_dataset,
)
from ubuntu_bio.validator import validate_local_dataset

runner = CliRunner()


def test_generate_readme_template() -> None:
    """Test generating a MIxS README with sequencing frontmatter."""
    content = generate_readme_template(
        title="Lassa Fever Surveillance",
        domain="virus",
        country="NG",
        taxon_id=11620,
        access="public",
        platform="ILLUMINA",
        library_strategy="WGS",
        library_layout="paired",
        sample_ids=["SMP_001"],
    )
    assert 'title: "Lassa Fever Surveillance"' in content
    assert "domain: virus" in content
    assert "countries: [NG]" in content
    assert "taxon_ids: [11620]" in content
    assert "platform: ILLUMINA" in content
    assert "library_strategy: WGS" in content
    assert "library_layout: paired" in content
    assert "SMP_001" in content


def test_generate_samples_tsv_template() -> None:
    """Test generating samples.tsv template."""
    content = generate_samples_tsv_template(
        domain="bacteria",
        country="GH",
        taxon_id=1392,
        sample_ids=["B_01", "B_02"],
    )
    lines = content.strip().split("\n")
    assert len(lines) == 3
    assert "sample_id\ttaxon_id\tcountry\tcollection_date" in lines[0]
    assert lines[1].startswith("B_01\t1392\tGH\t2024-01-15")


def test_generate_remote_files_template() -> None:
    """Test generating remote_files.tsv template."""
    content = generate_remote_files_template()
    assert "filename\turl\tmd5\tsize_bytes" in content


def test_init_dataset_success(tmp_path: Path) -> None:
    """Test successful dataset scaffolding into target directory."""
    target = tmp_path / "test_dataset"
    created = init_dataset(
        target_dir=target,
        title="Cholera Outbreak Study",
        domain="bacteria",
        country="KE",
        taxon_id=666,
    )
    assert (target / "README.md").is_file()
    assert (target / "samples.tsv").is_file()
    assert (target / "remote_files.tsv").is_file()
    assert (target / "reads").is_dir()
    assert created["readme"] == target / "README.md"


def test_init_dataset_prohibited_human_taxa(tmp_path: Path) -> None:
    """Test init_dataset rejects human taxon ID 9606."""
    target = tmp_path / "human_dataset"
    with pytest.raises(ClientValidationError, match=r"Human genomic data.*is strictly prohibited"):
        init_dataset(
            target_dir=target,
            title="Human Genomics",
            domain="metagenome",
            country="NG",
            taxon_id=9606,
        )


def test_init_dataset_invalid_country(tmp_path: Path) -> None:
    """Test init_dataset rejects non-AU country codes."""
    target = tmp_path / "invalid_country"
    with pytest.raises(ClientValidationError, match=r"must belong to the 54 African Union"):
        init_dataset(
            target_dir=target,
            title="Non-AU Dataset",
            domain="virus",
            country="US",
            taxon_id=10566,
        )


def test_validate_local_dataset_valid(tmp_path: Path) -> None:
    """Test validating a freshly scaffolded dataset where declared reads exist."""
    target = tmp_path / "valid_ds"
    init_dataset(
        target_dir=target,
        title="Valid Dataset",
        domain="virus",
        country="GH",
        taxon_id=10566,
    )

    # By default, template declares reads/SMP_001_1.fastq.gz and _2.fastq.gz, SMP_002_1 and _2
    for s in ["SMP_001", "SMP_002"]:
        (target / "reads" / f"{s}_1.fastq.gz").touch()
        (target / "reads" / f"{s}_2.fastq.gz").touch()

    result = validate_local_dataset(target)
    assert result.valid is True
    assert len(result.errors) == 0
    assert result.sample_count == 2
    assert result.library_count == 2


def test_validate_local_dataset_missing_readme(tmp_path: Path) -> None:
    """Test validation fails if README.md is missing."""
    target = tmp_path / "no_readme"
    target.mkdir()
    result = validate_local_dataset(target)
    assert result.valid is False
    assert any("README.md" in e.message for e in result.errors)


def test_validate_local_dataset_missing_declared_files(tmp_path: Path) -> None:
    """Test validation detects missing declared sequence files."""
    target = tmp_path / "missing_files_ds"
    init_dataset(
        target_dir=target,
        title="Missing Files Dataset",
        domain="virus",
        country="NG",
        taxon_id=10566,
    )
    # Files are declared in README.md but not created on disk
    result = validate_local_dataset(target)
    assert result.valid is False
    assert any("Missing declared sequence file" in e.message for e in result.errors)


def test_validate_local_dataset_orphaned_sequence_files(tmp_path: Path) -> None:
    """Test validation detects orphan sequence files on disk not declared in README."""
    target = tmp_path / "orphan_ds"
    init_dataset(
        target_dir=target,
        title="Orphan Dataset",
        domain="virus",
        country="NG",
        taxon_id=10566,
    )
    # Create declared files
    for s in ["SMP_001", "SMP_002"]:
        (target / "reads" / f"{s}_1.fastq.gz").touch()
        (target / "reads" / f"{s}_2.fastq.gz").touch()

    # Create an undeclared fastq file
    (target / "reads" / "orphan_sample.fastq.gz").touch()

    result = validate_local_dataset(target)
    assert result.valid is False
    assert any("Orphaned sequence file" in e.message for e in result.errors)


def test_cli_init_non_interactive(tmp_path: Path) -> None:
    """Test ubio init in non-interactive mode."""
    target = tmp_path / "cli_init_ds"
    result = runner.invoke(
        app,
        [
            "init",
            str(target),
            "-y",
            "-t",
            "Mpox Surveillance",
            "-d",
            "virus",
            "-c",
            "NG",
            "--taxon-id",
            "10244",
        ],
    )
    assert result.exit_code == 0
    assert "[SUCCESS] Dataset scaffolded successfully" in result.stdout
    assert (target / "README.md").is_file()
    assert (target / "samples.tsv").is_file()


def test_cli_init_prohibited_human(tmp_path: Path) -> None:
    """Test ubio init fails when given human taxon 9606."""
    target = tmp_path / "cli_human_ds"
    result = runner.invoke(
        app,
        [
            "init",
            str(target),
            "-y",
            "-t",
            "Human Study",
            "-d",
            "metagenome",
            "-c",
            "GH",
            "--taxon-id",
            "9606",
        ],
    )
    assert result.exit_code == 1
    assert "[ERROR] Validation failed:" in result.stdout
    assert "Human genomic data (Taxon ID 9606)" in result.stdout
    assert "prohibited" in result.stdout


def test_cli_check_command_pass(tmp_path: Path) -> None:
    """Test ubio check passes on compliant dataset."""
    target = tmp_path / "cli_check_ds"
    runner.invoke(
        app,
        [
            "init",
            str(target),
            "-y",
            "-t",
            "Valid CLI Dataset",
            "-d",
            "virus",
            "-c",
            "GH",
            "--taxon-id",
            "10566",
        ],
    )
    # Touch declared reads
    for s in ["SMP_001", "SMP_002"]:
        (target / "reads" / f"{s}_1.fastq.gz").touch()
        (target / "reads" / f"{s}_2.fastq.gz").touch()

    result = runner.invoke(app, ["check", str(target)])
    assert result.exit_code == 0
    assert "[PASSED] Dataset is valid and ready for upload." in result.stdout


def test_cli_check_command_fail(tmp_path: Path) -> None:
    """Test ubio check fails when declared sequence files are missing."""
    target = tmp_path / "cli_check_fail_ds"
    runner.invoke(
        app,
        [
            "init",
            str(target),
            "-y",
            "-t",
            "Fail CLI Dataset",
            "-d",
            "virus",
            "-c",
            "GH",
            "--taxon-id",
            "10566",
        ],
    )
    # Without creating files in reads/
    result = runner.invoke(app, ["check", str(target)])
    assert result.exit_code == 1
    assert "[FAILED] Dataset validation failed" in result.stdout
    assert "[ERROR]" in result.stdout
