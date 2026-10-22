"""Dataset scaffolding and template generation for UbuntuBio (M2-08)."""

from __future__ import annotations

import logging
from pathlib import Path

from ubuntu_bio.constants import (
    AU_COUNTRY_CODES,
    MANDATORY_SAMPLE_COLUMNS,
    PROHIBITED_TAXA,
    VALID_ACCESS_TIERS,
    VALID_DOMAINS,
    VALID_LAYOUTS,
    VALID_PLATFORMS,
    VALID_STRATEGIES,
)
from ubuntu_bio.exceptions import ClientValidationError

logger = logging.getLogger("ubuntu_bio.init")


def generate_readme_template(
    title: str,
    domain: str,
    country: str,
    taxon_id: int,
    access: str = "public",
    license_str: str = "cc-by-4.0",
    platform: str = "ILLUMINA",
    instrument_model: str = "Illumina MiSeq",
    library_strategy: str = "WGS",
    library_layout: str = "paired",
    nominal_length: int = 300,
    sample_ids: list[str] | None = None,
) -> str:
    """Generate a standard, MIxS-compliant README.md template with YAML frontmatter."""
    samples = sample_ids or ["SMP_001", "SMP_002"]
    layout_clean = library_layout.lower()
    platform_clean = platform.upper()
    strategy_clean = library_strategy.upper()

    libraries_yaml_lines: list[str] = []
    for idx, sid in enumerate(samples, start=1):
        lib_id = f"LIB_{idx:02d}"
        if layout_clean == "paired":
            files_block = f"""        - reads/{sid}_1.fastq.gz
        - reads/{sid}_2.fastq.gz"""
        else:
            files_block = f"""        - reads/{sid}.fastq.gz"""

        libraries_yaml_lines.append(
            f"""    - library_id: {lib_id}
      sample_name: {sid}
      title: "{strategy_clean} library for {sid}"
      file_type: FASTQ
      filenames:
{files_block}"""
        )

    libraries_block = "\n".join(libraries_yaml_lines)

    nominal_length_line = (
        f"  nominal_length: {nominal_length}\n" if layout_clean == "paired" else ""
    )

    benefit_sharing_line = (
        'benefit_sharing: "Data use agreement required for commercial downstream utilization."\n'
        if access == "gated"
        else ""
    )

    return f"""---
title: "{title}"
domain: {domain.lower()}
access: {access.lower()}
license: {license_str.lower()}
countries: [{country.upper()}]
taxon_ids: [{taxon_id}]
data_types: [reads]
{benefit_sharing_line}
# Sequencing Experiment & Library Metadata
sequencing:
  platform: {platform_clean}
  instrument_model: "{instrument_model}"
  library_strategy: {strategy_clean}
  library_source: GENOMIC
  library_selection: PCR
  library_layout: {layout_clean}
{nominal_length_line}  demultiplexed: true
  design_description: >
    DNA extraction and sequencing library preparation protocol.
  libraries:
{libraries_block}
---

# {title}

## Study Overview
Briefly describe the research questions, geographical scope, and surveillance goals of this project.

## Methodology & Biosafety
* Extraction Method: [Insert extraction kit, e.g. QIAamp DNA Mini Kit]
* Sequencing Platform: {platform_clean} ({instrument_model})
* Biosafety Level: [BSL-2 / BSL-3]

## Author & Institutional Attribution
* Lead Institution: [Insert African Institution / University]
* Primary Investigators: [Insert Researcher Names and ORCID iDs]
* Funding & Grants: [Insert NIH, Wellcome Trust, or National Grant IDs]
"""


def generate_samples_tsv_template(
    domain: str,
    country: str,
    taxon_id: int,
    sample_ids: list[str] | None = None,
) -> str:
    """Generate samples.tsv adhering strictly to the MIxS African schema."""
    header = "\t".join(MANDATORY_SAMPLE_COLUMNS)
    samples = sample_ids or ["SMP_001", "SMP_002"]

    # Provide reasonable defaults based on domain
    host = "Homo sapiens" if domain.lower() in ("virus", "bacteria") else "Environment"
    iso_source = "blood" if domain.lower() in ("virus", "bacteria") else "soil"

    rows: list[str] = [header]
    for idx, sid in enumerate(samples, start=1):
        date_str = f"2024-0{idx:01d}-15" if idx < 10 else "2024-10-15"
        rows.append(f"{sid}\t{taxon_id}\t{country.upper()}\t{date_str}\t\t\t\t{host}\t{iso_source}")

    return "\n".join(rows) + "\n"


def generate_remote_files_template() -> str:
    """Generate remote_files.tsv template for external fastq mirrors."""
    return (
        "# Remote sequence file manifest (optional)\n"
        "# Format: filename<tab>url<tab>md5<tab>size_bytes\n"
        "filename\turl\tmd5\tsize_bytes\n"
        "# reads/sample_1.fastq.gz\thttps://ftp.sra.ebi.ac.uk/sample_1.fastq.gz\t"
        "d41d8cd98f00b204e9800998ecf8427e\t1048576\n"
    )


def init_dataset(
    target_dir: Path,
    title: str,
    domain: str,
    country: str,
    taxon_id: int,
    access: str = "public",
    license_str: str = "cc-by-4.0",
    platform: str = "ILLUMINA",
    instrument_model: str = "Illumina MiSeq",
    library_strategy: str = "WGS",
    library_layout: str = "paired",
    nominal_length: int = 300,
    sample_ids: list[str] | None = None,
) -> dict[str, Path]:
    """Scaffold a new UbuntuBio dataset directory with templates and directory layout.

    Returns a mapping of created file and folder paths.
    """
    logger.debug("Initializing dataset in directory: %s", target_dir)

    # Validate parameters
    domain_clean = domain.strip().lower()
    if domain_clean not in VALID_DOMAINS:
        raise ClientValidationError(
            f"Invalid domain '{domain}'. Permitted domains: {sorted(VALID_DOMAINS)}"
        )

    country_clean = country.strip().upper()
    if country_clean not in AU_COUNTRY_CODES:
        raise ClientValidationError(
            f"Country code '{country}' must belong to the 54 African Union member states."
        )

    if taxon_id in PROHIBITED_TAXA:
        raise ClientValidationError(
            f"Human genomic data (Taxon ID {taxon_id}) is strictly prohibited in UbuntuBio v1."
        )
    if taxon_id <= 0:
        raise ClientValidationError(f"Taxon ID must be a positive integer, got {taxon_id}.")

    access_clean = access.strip().lower()
    if access_clean not in VALID_ACCESS_TIERS:
        raise ClientValidationError(
            f"Invalid access tier '{access}'. Permitted: {sorted(VALID_ACCESS_TIERS)}"
        )

    platform_clean = platform.strip().upper()
    if platform_clean not in VALID_PLATFORMS:
        raise ClientValidationError(
            f"Invalid platform '{platform}'. Permitted: {sorted(VALID_PLATFORMS)}"
        )

    strategy_clean = library_strategy.strip().upper()
    if strategy_clean not in VALID_STRATEGIES:
        raise ClientValidationError(
            f"Invalid library strategy '{library_strategy}'. Permitted: {sorted(VALID_STRATEGIES)}"
        )

    layout_clean = library_layout.strip().lower()
    if layout_clean not in VALID_LAYOUTS:
        raise ClientValidationError(
            f"Invalid layout '{library_layout}'. Permitted: {sorted(VALID_LAYOUTS)}"
        )

    if layout_clean == "paired" and nominal_length <= 0:
        raise ClientValidationError("nominal_length must be a positive integer for paired layout.")

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Failed to create target directory '%s': %s", target_dir, exc)
        raise ClientValidationError(f"Cannot create directory '{target_dir}': {exc}") from exc

    # Generate files
    readme_path = target_dir / "README.md"
    samples_path = target_dir / "samples.tsv"
    remote_path = target_dir / "remote_files.tsv"
    reads_dir = target_dir / "reads"

    try:
        readme_content = generate_readme_template(
            title=title,
            domain=domain_clean,
            country=country_clean,
            taxon_id=taxon_id,
            access=access_clean,
            license_str=license_str,
            platform=platform_clean,
            instrument_model=instrument_model,
            library_strategy=strategy_clean,
            library_layout=layout_clean,
            nominal_length=nominal_length,
            sample_ids=sample_ids,
        )
        readme_path.write_text(readme_content, encoding="utf-8")

        samples_content = generate_samples_tsv_template(
            domain=domain_clean,
            country=country_clean,
            taxon_id=taxon_id,
            sample_ids=sample_ids,
        )
        samples_path.write_text(samples_content, encoding="utf-8")

        remote_content = generate_remote_files_template()
        remote_path.write_text(remote_content, encoding="utf-8")

        reads_dir.mkdir(exist_ok=True)
    except OSError as exc:
        logger.error("File write error during dataset initialization: %s", exc)
        raise ClientValidationError(
            f"Failed writing template files to '{target_dir}': {exc}"
        ) from exc

    logger.info("Successfully initialized dataset at '%s'", target_dir)
    return {
        "readme": readme_path,
        "samples": samples_path,
        "remote_files": remote_path,
        "reads": reads_dir,
    }
