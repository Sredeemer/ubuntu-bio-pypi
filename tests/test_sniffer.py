"""Unit tests for sequence format sniffing and biological quality screening (T-SNIFF-01..12)."""

from __future__ import annotations

import gzip
from pathlib import Path

from typer.testing import CliRunner

from ubuntu_bio.cli import app
from ubuntu_bio.constants import BAM_MAGIC
from ubuntu_bio.scaffold import init_dataset
from ubuntu_bio.sniffer import (
    SequenceSniffResult,
    sniff_magic_bytes,
    sniff_sequence_file,
)
from ubuntu_bio.validator import validate_local_dataset

runner = CliRunner()


def test_sniff_magic_bytes_raw_and_compressed(tmp_path: Path) -> None:
    """Test identifying magic bytes across gzip, raw fastq, raw fasta, and bam."""
    fq_path = tmp_path / "sample.fastq"
    fq_path.write_text("@read_1\nACGT\n+\nIIII\n", encoding="utf-8")
    fmt, comp, _ = sniff_magic_bytes(fq_path)
    assert fmt == "FASTQ"
    assert comp == "RAW"

    gz_path = tmp_path / "sample.fastq.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        f.write("@read_1\nACGT\n+\nIIII\n")
    fmt_gz, comp_gz, _ = sniff_magic_bytes(gz_path)
    assert fmt_gz == "GZIP"
    assert comp_gz == "GZIP"

    fa_path = tmp_path / "sample.fasta"
    fa_path.write_text(">contig_1\nACGTACGT\n", encoding="utf-8")
    fmt_fa, comp_fa, _ = sniff_magic_bytes(fa_path)
    assert fmt_fa == "FASTA"
    assert comp_fa == "RAW"

    bam_path = tmp_path / "sample.bam"
    bam_path.write_bytes(BAM_MAGIC + b"\x00\x00")
    fmt_bam, comp_bam, _ = sniff_magic_bytes(bam_path)
    assert fmt_bam == "BAM"
    assert comp_bam == "NONE"


def test_sniff_valid_raw_fastq(tmp_path: Path) -> None:
    """Test sniffing a valid raw FASTQ with Sanger Phred+33 scores."""
    fq = tmp_path / "reads.fastq"
    content = (
        "@ERR001.1 instrument_run_1/1\n"
        "GCATGCATGCATGCAT\n"
        "+\n"
        "IIIIIIIIIIIIIIII\n"
        "@ERR001.2 instrument_run_1/2\n"
        "GGGGCCCCAAAATTTT\n"
        "+\n"
        "JJJJJJJJJJJJJJJJ\n"
    )
    fq.write_text(content, encoding="utf-8")

    result: SequenceSniffResult = sniff_sequence_file(fq)
    assert result.format == "FASTQ"
    assert result.compression == "RAW"
    assert result.is_valid is True
    assert result.reads_sampled == 2
    assert result.mean_read_length == 16.0
    assert result.gc_percent == 50.0
    assert result.phred_encoding == "Phred+33"
    assert len(result.errors) == 0


def test_sniff_valid_gzipped_fastq(tmp_path: Path) -> None:
    """Test streaming sniffing of a gzipped FASTQ file."""
    gz_file = tmp_path / "reads.fastq.gz"
    with gzip.open(gz_file, "wt", encoding="utf-8") as f:
        for idx in range(10):
            f.write(f"@read_{idx}\nACGTACGTACGT\n+\nIIIIIIIIIIII\n")

    result = sniff_sequence_file(gz_file)
    assert result.format == "FASTQ"
    assert result.compression == "GZIP"
    assert result.is_valid is True
    assert result.reads_sampled == 10
    assert result.mean_read_length == 12.0
    assert result.phred_encoding == "Phred+33"


def test_sniff_fastq_length_mismatch(tmp_path: Path) -> None:
    """Test flagging FASTQ record where sequence length does not match quality length."""
    fq = tmp_path / "corrupt.fastq"
    content = (
        "@bad_read_1\n"
        "ACGTACGTACGT\n"  # 12 bp
        "+\n"
        "IIII\n"  # 4 chars -> mismatch
    )
    fq.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fq)
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert any("length mismatch" in e.message for e in result.errors)


def test_sniff_fastq_corrupt_separator(tmp_path: Path) -> None:
    """Test flagging FASTQ record where 3rd line does not start with '+'."""
    fq = tmp_path / "bad_sep.fastq"
    content = "@read_1\nACGT\nnot_a_plus_separator\nIIII\n"
    fq.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fq)
    assert result.is_valid is False
    assert any("separator line must begin with '+'" in e.message for e in result.errors)


def test_sniff_fastq_legacy_phred64_warning(tmp_path: Path) -> None:
    """Test detecting legacy Illumina 1.3/1.5 Phred+64 quality encoding."""
    fq = tmp_path / "legacy.fastq"
    content = (
        "@legacy_read_1\n"
        "ACGTACGT\n"
        "+\n"
        "ghghghgh\n"  # ASCII 103, 104 -> Phred+64
        "@legacy_read_2\n"
        "ACGTACGT\n"
        "+\n"
        "BBBBBBBB\n"  # ASCII 66
    )
    fq.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fq)
    assert result.phred_encoding == "Phred+64"
    assert len(result.warnings) > 0
    assert any("Phred+64" in w.message for w in result.warnings)


def test_sniff_empty_sequence_file(tmp_path: Path) -> None:
    """Test sniffing a 0-byte sequence file emits a warning."""
    empty = tmp_path / "empty.fastq"
    empty.touch()

    result = sniff_sequence_file(empty)
    assert result.format == "EMPTY"
    assert result.is_valid is True  # Warning level does not fail unless strict
    assert any("empty (0 bytes)" in w.message for w in result.warnings)


def test_sniff_corrupted_gzip_file(tmp_path: Path) -> None:
    """Test sniffing a file with a corrupt gzip stream fails cleanly."""
    corrupt_gz = tmp_path / "corrupt.fastq.gz"
    # Write gzip magic bytes followed by garbage
    corrupt_gz.write_bytes(b"\x1f\x8b\x08\x00garbage_data_that_cannot_decompress")

    result = sniff_sequence_file(corrupt_gz)
    assert result.is_valid is False
    assert any("Corrupted gzip" in e.message for e in result.errors)


def test_sniff_valid_fasta(tmp_path: Path) -> None:
    """Test sniffing a valid FASTA contig file."""
    fa = tmp_path / "contigs.fasta"
    content = (
        ">isolate_1 Cholera vibrio contig 1\n"
        "GCATGCATGCAT\n"
        "GCATGCATGCAT\n"
        ">isolate_2 Cholera vibrio contig 2\n"
        "ATATATATATAT\n"
    )
    fa.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fa)
    assert result.format == "FASTA"
    assert result.is_valid is True
    assert result.reads_sampled == 2
    assert result.mean_read_length == 18.0


def test_sniff_fasta_human_chromosome_header_rejection(tmp_path: Path) -> None:
    """Test detecting human chromosome headers in FASTA records."""
    fa = tmp_path / "human_contig.fasta"
    content = ">chr1 Homo sapiens chromosome 1, GRCh38.p14 primary assembly\nACGTACGTACGT\n"
    fa.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fa)
    assert result.human_markers_detected is True
    assert any("Human reference" in e.message for e in result.errors)


def test_sniff_human_signature_kmers_warning(tmp_path: Path) -> None:
    """Test warning when sampled reads match canonical human rRNA/mtDNA signatures."""
    fq = tmp_path / "human_host_reads.fastq"
    # Construct 10 reads containing the canonical human 28S marker
    marker = "CGCGACCTCAGATCAGACGTGGCGA"
    lines: list[str] = []
    for i in range(10):
        lines.append(f"@read_{i}")
        lines.append(f"AAAA{marker}TTTT")
        lines.append("+")
        lines.append("I" * (len(marker) + 8))

    fq.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = sniff_sequence_file(fq)
    assert result.human_markers_detected is True
    assert any("human host contamination" in w.message.lower() for w in result.warnings)


def test_ubio_check_displays_sequence_screening_table(tmp_path: Path) -> None:
    """Integration test verifying ubio check runs the sequence sniffer and prints table."""
    ds_dir = tmp_path / "screen_dataset"
    init_dataset(
        target_dir=ds_dir,
        title="Cholera Surveillance",
        domain="bacteria",
        country="GH",
        taxon_id=666,
    )

    # Write real valid gzipped reads for SMP_001 and SMP_002
    for s in ["SMP_001", "SMP_002"]:
        for pair in ["1", "2"]:
            p = ds_dir / "reads" / f"{s}_{pair}.fastq.gz"
            with gzip.open(p, "wt", encoding="utf-8") as f:
                f.write(f"@{s}_{pair}.1 read\nGCATGCATGCAT\n+\nIIIIIIIIIIII\n")

    # Run validation engine
    result = validate_local_dataset(ds_dir)
    assert result.valid is True
    assert len(result.sniff_results) == 4
    for sn in result.sniff_results:
        assert sn.format == "FASTQ"
        assert sn.compression == "GZIP"
        assert sn.reads_sampled == 1

    # Run CLI check
    cli_res = runner.invoke(app, ["check", str(ds_dir)])
    assert cli_res.exit_code == 0
    assert "Sequence File Screening Diagnostics" in cli_res.stdout
    assert "FASTQ (GZIP)" in cli_res.stdout
    assert "PASSED" in cli_res.stdout
