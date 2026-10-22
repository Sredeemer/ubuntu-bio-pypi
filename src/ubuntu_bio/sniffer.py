"""Biological sequence format sniffer and quality screening engine (M2-09).

Performs low-latency, bounded streaming inspection on FASTQ, FASTA, and BAM files
to verify magic bytes, record structure, Phred quality encoding, GC metrics, and
screen for accidental human host genomic contamination.
"""

from __future__ import annotations

import gzip
import io
import logging
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from ubuntu_bio.constants import (
    BAM_MAGIC,
    CRAM_MAGIC,
    GZIP_MAGIC,
    HUMAN_HEADER_REGEX,
    HUMAN_SIGNATURE_KMERS,
)
from ubuntu_bio.validator import ValidationIssue

logger = logging.getLogger("ubuntu_bio.sniffer")

KMER_SIZE: Final[int] = 25


@dataclass(frozen=True)
class SequenceSniffResult:
    """Detailed biological sanity screening output for a sequence file."""

    file_path: str
    format: str  # "FASTQ", "FASTA", "BAM", "CRAM", "UNKNOWN", "EMPTY"
    compression: str  # "GZIP", "RAW", "NONE"
    is_valid: bool
    reads_sampled: int = 0
    mean_read_length: float = 0.0
    min_read_length: int = 0
    max_read_length: int = 0
    gc_percent: float = 0.0
    n_base_percent: float = 0.0
    phred_encoding: str = "UNKNOWN"  # "Phred+33", "Phred+64", "UNKNOWN"
    human_markers_detected: bool = False
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


def _extract_kmers(seq: str, k: int = KMER_SIZE) -> set[str]:
    """Extract all k-mers of length k from sequence."""
    if len(seq) < k:
        return set()
    return {seq[i : i + k] for i in range(len(seq) - k + 1)}


def _has_human_marker(seq_upper: str) -> bool:
    """Check if sequence matches any canonical human rRNA/mtDNA k-mer marker."""
    kmers = _extract_kmers(seq_upper, KMER_SIZE)
    return bool(kmers.intersection(HUMAN_SIGNATURE_KMERS))


def sniff_magic_bytes(file_path: Path) -> tuple[str, str, bytes]:
    """Inspect the first bytes of a file to determine compression and format.

    Returns (format_guess, compression_type, leading_bytes).
    """
    try:
        size = file_path.stat().st_size
        if size == 0:
            return "EMPTY", "NONE", b""
    except OSError as exc:
        logger.error("Failed to stat sequence file '%s': %s", file_path, exc)
        return "ERROR", "NONE", b""

    try:
        with file_path.open("rb") as f:
            header = f.read(16)
    except OSError as exc:
        logger.error("Failed to read header bytes from '%s': %s", file_path, exc)
        return "ERROR", "NONE", b""

    if header.startswith(GZIP_MAGIC):
        return "GZIP", "GZIP", header
    if header.startswith(BAM_MAGIC):
        return "BAM", "NONE", header
    if header.startswith(CRAM_MAGIC):
        return "CRAM", "NONE", header

    # Plain text format guess
    if header.startswith(b"@"):
        return "FASTQ", "RAW", header
    if header.startswith(b">"):
        return "FASTA", "RAW", header

    return "UNKNOWN", "RAW", header


def sniff_fastq_stream(
    stream: Iterable[str],
    file_str: str,
    compression: str,
    max_reads: int = 2000,
) -> SequenceSniffResult:
    """Screen FASTQ stream records for 4-line structure, quality encoding, and metrics."""
    issues: list[ValidationIssue] = []
    reads_sampled = 0
    total_length = 0
    min_len = 0
    max_len = 0
    gc_count = 0
    n_count = 0
    total_bases = 0
    min_q_ascii = 127
    max_q_ascii = 0
    human_marker_hits = 0

    it = iter(stream)
    line_num = 0

    while reads_sampled < max_reads:
        try:
            line1 = next(it, None)
            if line1 is None:
                break
            line_num += 1

            line1 = line1.strip()
            if not line1:
                continue

            if not line1.startswith("@"):
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num,
                        message=(
                            f"FASTQ record #{reads_sampled + 1} header line must begin with '@', "
                            f"got '{line1[:30]}'."
                        ),
                    )
                )
                break

            # Check header for human indicators
            if HUMAN_HEADER_REGEX.search(line1):
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num,
                        column="header",
                        message=(
                            f"Human chromosome/assembly indicator detected in FASTQ header: "
                            f"'{line1[:50]}'. Human genomic data is prohibited in v1."
                        ),
                    )
                )

            # Line 2: Sequence
            line2 = next(it, None)
            if line2 is None:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num + 1,
                        message=(
                            f"Premature EOF in FASTQ record #{reads_sampled + 1} "
                            "(sequence line missing)."
                        ),
                    )
                )
                break
            line_num += 1
            seq = line2.strip()
            seq_len = len(seq)

            # Line 3: Separator (+)
            line3 = next(it, None)
            if line3 is None:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num + 1,
                        message=(
                            f"Premature EOF in FASTQ record #{reads_sampled + 1} "
                            "(separator line missing)."
                        ),
                    )
                )
                break
            line_num += 1
            sep = line3.strip()
            if not sep.startswith("+"):
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num,
                        message=(
                            f"FASTQ record #{reads_sampled + 1} separator line "
                            f"must begin with '+', got '{sep[:20]}'."
                        ),
                    )
                )
                break

            # Line 4: Quality string
            line4 = next(it, None)
            if line4 is None:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num + 1,
                        message=(
                            f"Premature EOF in FASTQ record #{reads_sampled + 1} "
                            "(quality line missing)."
                        ),
                    )
                )
                break
            line_num += 1
            qual = line4.strip()

            if len(qual) != seq_len:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num,
                        column="quality",
                        message=(
                            f"FASTQ record #{reads_sampled + 1} length mismatch: "
                            f"sequence length ({seq_len}) != quality length ({len(qual)})."
                        ),
                    )
                )
                break

            # Accumulate metrics
            reads_sampled += 1
            total_length += seq_len
            min_len = seq_len if min_len == 0 else min(min_len, seq_len)
            max_len = max(max_len, seq_len)

            seq_upper = seq.upper()
            gc_count += seq_upper.count("G") + seq_upper.count("C")
            n_count += seq_upper.count("N")
            total_bases += seq_len

            # Check quality scores
            for char in qual:
                ascii_val = ord(char)
                min_q_ascii = min(min_q_ascii, ascii_val)
                max_q_ascii = max(max_q_ascii, ascii_val)

            # Screen for human markers
            if _has_human_marker(seq_upper):
                human_marker_hits += 1

        except Exception as exc:
            logger.error("Error reading FASTQ record in '%s': %s", file_str, exc)
            issues.append(
                ValidationIssue(
                    file=file_str,
                    line=line_num,
                    message=f"Corrupted FASTQ stream: {exc}",
                )
            )
            break

    if reads_sampled == 0 and not issues:
        issues.append(
            ValidationIssue(
                file=file_str,
                message="FASTQ file contains no valid sequence records.",
            )
        )

    # Determine Phred scale
    phred_scale = "UNKNOWN"
    if reads_sampled > 0:
        if min_q_ascii < 58:
            phred_scale = "Phred+33"
        elif min_q_ascii >= 64 and max_q_ascii > 74:
            phred_scale = "Phred+64"
            issues.append(
                ValidationIssue(
                    file=file_str,
                    message=(
                        f"Legacy Illumina 1.3/1.5 Phred+64 quality encoding detected "
                        f"(ASCII range {min_q_ascii}-{max_q_ascii}). "
                        "Modern pipelines standard is Phred+33."
                    ),
                    severity="warning",
                )
            )
        else:
            phred_scale = "Phred+33"

    # Metric calculations
    mean_len = (total_length / reads_sampled) if reads_sampled > 0 else 0.0
    gc_pct = (gc_count / total_bases * 100.0) if total_bases > 0 else 0.0
    n_pct = (n_count / total_bases * 100.0) if total_bases > 0 else 0.0

    # N-base warning
    if n_pct > 15.0:
        issues.append(
            ValidationIssue(
                file=file_str,
                message=(
                    f"High ambiguous base percentage ({n_pct:.1f}% Ns across sampled reads). "
                    "Sequence data may have severe quality degradation."
                ),
                severity="warning",
            )
        )

    # Human marker contamination check
    human_detected = False
    if reads_sampled >= 10 and (human_marker_hits / reads_sampled) >= 0.20:
        human_detected = True
        pct_hit = (human_marker_hits / reads_sampled) * 100.0
        issues.append(
            ValidationIssue(
                file=file_str,
                message=(
                    f"Potential undepleted human host contamination detected: "
                    f"{human_marker_hits}/{reads_sampled} sampled reads ({pct_hit:.1f}%) "
                    "matched human rRNA/mtDNA marker signatures. Human genomic data is "
                    "prohibited in UbuntuBio v1."
                ),
                severity="warning",
            )
        )

    has_errors = any(i.severity == "error" for i in issues)

    return SequenceSniffResult(
        file_path=file_str,
        format="FASTQ",
        compression=compression,
        is_valid=not has_errors,
        reads_sampled=reads_sampled,
        mean_read_length=round(mean_len, 2),
        min_read_length=min_len,
        max_read_length=max_len,
        gc_percent=round(gc_pct, 2),
        n_base_percent=round(n_pct, 2),
        phred_encoding=phred_scale,
        human_markers_detected=human_detected,
        issues=issues,
    )


def sniff_fasta_stream(
    stream: Iterable[str],
    file_str: str,
    compression: str,
    max_records: int = 2000,
) -> SequenceSniffResult:
    """Screen FASTA stream records for contig headers, length, GC%, and human assembly markers."""
    issues: list[ValidationIssue] = []
    records_sampled = 0
    total_length = 0
    min_len = 0
    max_len = 0
    gc_count = 0
    n_count = 0
    total_bases = 0
    human_detected = False

    current_header = ""
    current_seq_parts: list[str] = []
    line_num = 0

    def _flush_record(header: str, seq_str: str, rec_idx: int) -> None:
        nonlocal records_sampled, total_length, min_len, max_len
        nonlocal gc_count, n_count, total_bases, human_detected

        if not header:
            return

        records_sampled += 1
        seq_len = len(seq_str)
        total_length += seq_len
        min_len = seq_len if min_len == 0 else min(min_len, seq_len)
        max_len = max(max_len, seq_len)

        seq_upper = seq_str.upper()
        gc_count += seq_upper.count("G") + seq_upper.count("C")
        n_count += seq_upper.count("N")
        total_bases += seq_len

        # Screen header for human chromosomal markers
        if HUMAN_HEADER_REGEX.search(header):
            human_detected = True
            issues.append(
                ValidationIssue(
                    file=file_str,
                    line=rec_idx,
                    column="header",
                    message=(
                        f"Human reference / chromosome detected in FASTA header: '{header[:50]}'. "
                        "Human genomic data is prohibited in v1."
                    ),
                )
            )

        if _has_human_marker(seq_upper):
            human_detected = True

    for line in stream:
        line_num += 1
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith(">"):
            if current_header:
                _flush_record(current_header, "".join(current_seq_parts), line_num)
                current_seq_parts.clear()
                if records_sampled >= max_records:
                    break
            current_header = stripped[1:].strip()
            if not current_header:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num,
                        message="Empty FASTA header line encountered.",
                    )
                )
        else:
            if not current_header:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        line=line_num,
                        message=f"FASTA sequence data before initial header: '{stripped[:30]}'.",
                    )
                )
                break
            current_seq_parts.append(stripped)

    if current_header and records_sampled < max_records:
        _flush_record(current_header, "".join(current_seq_parts), line_num)

    if records_sampled == 0 and not issues:
        issues.append(
            ValidationIssue(
                file=file_str,
                message="FASTA file contains no valid sequence records.",
            )
        )

    mean_len = (total_length / records_sampled) if records_sampled > 0 else 0.0
    gc_pct = (gc_count / total_bases * 100.0) if total_bases > 0 else 0.0
    n_pct = (n_count / total_bases * 100.0) if total_bases > 0 else 0.0

    has_errors = any(i.severity == "error" for i in issues)

    return SequenceSniffResult(
        file_path=file_str,
        format="FASTA",
        compression=compression,
        is_valid=not has_errors,
        reads_sampled=records_sampled,
        mean_read_length=round(mean_len, 2),
        min_read_length=min_len,
        max_read_length=max_len,
        gc_percent=round(gc_pct, 2),
        n_base_percent=round(n_pct, 2),
        phred_encoding="NONE",
        human_markers_detected=human_detected,
        issues=issues,
    )


def sniff_bam_file(file_path: Path) -> SequenceSniffResult:
    """Inspect BAM header bytes for magic bytes and human reference contigs."""
    issues: list[ValidationIssue] = []
    human_detected = False
    file_str = str(file_path)

    try:
        with file_path.open("rb") as raw_f:
            magic = raw_f.read(4)
            if magic != BAM_MAGIC:
                issues.append(
                    ValidationIssue(
                        file=file_str,
                        message=f"Invalid BAM magic bytes. Expected 'BAM\\1', got {magic!r}.",
                    )
                )
                return SequenceSniffResult(
                    file_path=file_str,
                    format="BAM",
                    compression="NONE",
                    is_valid=False,
                    issues=issues,
                )

        # BAM header is BGZF-compressed text. Decompress first block with gzip.
        try:
            with gzip.open(file_path, "rb") as gz_f:
                header_data = gz_f.read(65536)  # Read up to 64KB of SAM header
                # Extract text lines
                text = header_data.decode("utf-8", errors="ignore")
                for line in text.splitlines():
                    if line.startswith("@SQ") and HUMAN_HEADER_REGEX.search(line):
                        human_detected = True
                        issues.append(
                            ValidationIssue(
                                file=file_str,
                                column="header",
                                message=(
                                    f"Human reference contig detected in BAM header: "
                                    f"'{line[:60]}'. Human genomic data is prohibited in v1."
                                ),
                            )
                        )
                        break
        except Exception as exc:
            logger.debug("Non-critical BAM BGZF header parsing warning on '%s': %s", file_str, exc)

    except OSError as exc:
        logger.error("Failed opening BAM file '%s': %s", file_path, exc)
        issues.append(
            ValidationIssue(
                file=file_str,
                message=f"Could not open BAM file: {exc}",
            )
        )

    has_errors = any(i.severity == "error" for i in issues)

    return SequenceSniffResult(
        file_path=file_str,
        format="BAM",
        compression="NONE",
        is_valid=not has_errors,
        reads_sampled=0,
        mean_read_length=0.0,
        min_read_length=0,
        max_read_length=0,
        gc_percent=0.0,
        n_base_percent=0.0,
        phred_encoding="UNKNOWN",
        human_markers_detected=human_detected,
        issues=issues,
    )


def sniff_sequence_file(file_path: Path, max_reads: int = 2000) -> SequenceSniffResult:
    """Perform streaming biological sanity screening on a local sequence file.

    Inspects magic bytes, format structure (FASTQ/FASTA/BAM), Phred scale,
    GC content %, and screens for human reference contamination.
    """
    file_str = str(file_path)
    logger.debug("Sniffing sequence file: %s", file_path)

    if not file_path.exists():
        return SequenceSniffResult(
            file_path=file_str,
            format="UNKNOWN",
            compression="NONE",
            is_valid=False,
            issues=[
                ValidationIssue(
                    file=file_str,
                    message=f"Sequence file not found: '{file_str}'.",
                )
            ],
        )

    fmt_guess, compression, _ = sniff_magic_bytes(file_path)

    if fmt_guess == "EMPTY":
        return SequenceSniffResult(
            file_path=file_str,
            format="EMPTY",
            compression="NONE",
            is_valid=True,
            issues=[
                ValidationIssue(
                    file=file_str,
                    message="Sequence file is empty (0 bytes).",
                    severity="warning",
                )
            ],
        )

    if fmt_guess == "BAM":
        return sniff_bam_file(file_path)

    if fmt_guess == "CRAM":
        return SequenceSniffResult(
            file_path=file_str,
            format="CRAM",
            compression="NONE",
            is_valid=True,
            issues=[],
        )

    # For Gzip or Raw text files
    try:
        with (
            gzip.open(file_path, "rt", encoding="utf-8", errors="replace")
            if compression == "GZIP"
            else file_path.open("rt", encoding="utf-8", errors="replace")
        ) as f_obj:
            # Peek first non-empty line
            first_line = ""
            for raw_line in f_obj:
                s = raw_line.strip()
                if s:
                    first_line = s
                    break

            if not first_line:
                return SequenceSniffResult(
                    file_path=file_str,
                    format="EMPTY",
                    compression=compression,
                    is_valid=False,
                    issues=[
                        ValidationIssue(
                            file=file_str,
                            message="Sequence file contains no lines.",
                        )
                    ],
                )

            # Rewind by chaining first_line back with remaining stream
            combined_stream = io.StringIO(first_line + "\n")
            chain_stream: Iterable[str] = (
                line for stream in (combined_stream, f_obj) for line in stream
            )

            if first_line.startswith("@"):
                return sniff_fastq_stream(
                    stream=chain_stream,
                    file_str=file_str,
                    compression=compression,
                    max_reads=max_reads,
                )
            elif first_line.startswith(">"):
                return sniff_fasta_stream(
                    stream=chain_stream,
                    file_str=file_str,
                    compression=compression,
                    max_records=max_reads,
                )
            else:
                return SequenceSniffResult(
                    file_path=file_str,
                    format="UNKNOWN",
                    compression=compression,
                    is_valid=False,
                    issues=[
                        ValidationIssue(
                            file=file_str,
                            message=(
                                f"Unrecognized sequence record format. First line must start "
                                f"with '@' (FASTQ) or '>' (FASTA), got '{first_line[:30]}'."
                            ),
                        )
                    ],
                )

    except (gzip.BadGzipFile, zlib.error) as exc:
        return SequenceSniffResult(
            file_path=file_str,
            format="UNKNOWN",
            compression="GZIP",
            is_valid=False,
            issues=[
                ValidationIssue(
                    file=file_str,
                    message=f"Corrupted gzip stream in sequence file: {exc}",
                )
            ],
        )
    except OSError as exc:
        logger.error("Failed opening sequence file '%s': %s", file_path, exc)
        return SequenceSniffResult(
            file_path=file_str,
            format="UNKNOWN",
            compression=compression,
            is_valid=False,
            issues=[
                ValidationIssue(
                    file=file_str,
                    message=f"Could not read sequence file: {exc}",
                )
            ],
        )
