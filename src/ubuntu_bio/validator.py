"""Local preflight dataset validation engine for UbuntuBio (M2-08)."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ubuntu_bio.constants import (
    AFRICA_LAT_MAX,
    AFRICA_LAT_MIN,
    AFRICA_LON_MAX,
    AFRICA_LON_MIN,
    AU_COUNTRY_CODES,
    MANDATORY_SAMPLE_COLUMNS,
    PROHIBITED_TAXA,
    SEQUENCE_FILE_EXTENSIONS,
    VALID_DOMAINS,
    VALID_FILE_TYPES,
    VALID_LAYOUTS,
    VALID_PLATFORMS,
    VALID_STRATEGIES,
)

logger = logging.getLogger("ubuntu_bio.validator")

DATE_REGEX = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")

DEFAULT_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".github",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".DS_Store",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    """An individual warning or error identified during dataset validation."""

    file: str
    message: str
    line: int | None = None
    column: str | None = None
    severity: str = "error"  # "error" | "warning"

    @property
    def level(self) -> str:
        return self.severity

    @property
    def field(self) -> str | None:
        return self.column


@dataclass(frozen=True)
class ValidationResult:
    """Aggregated validation output for a local dataset directory."""

    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    sample_count: int = 0
    remote_file_count: int = 0
    library_count: int = 0
    sniff_results: list[Any] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.is_valid

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


def _extract_frontmatter(text: str) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
    """Extract and parse YAML frontmatter between leading '---' boundaries."""
    issues: list[ValidationIssue] = []
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        issues.append(
            ValidationIssue(
                file="README.md",
                line=1,
                message="README.md must begin with a '---' YAML front-matter boundary.",
                severity="error",
            )
        )
        return None, issues

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        issues.append(
            ValidationIssue(
                file="README.md",
                line=len(lines),
                message="Unterminated YAML front-matter in README.md; missing closing '---'.",
                severity="error",
            )
        )
        return None, issues

    yaml_block = "\n".join(lines[1:end_idx])
    try:
        parsed = yaml.safe_load(yaml_block)
        if not isinstance(parsed, dict):
            issues.append(
                ValidationIssue(
                    file="README.md",
                    line=1,
                    message="YAML front-matter in README.md must be a key-value mapping.",
                    severity="error",
                )
            )
            return None, issues
        return parsed, issues
    except yaml.YAMLError as exc:
        logger.debug("YAML syntax error parsing README.md: %s", exc)
        issues.append(
            ValidationIssue(
                file="README.md",
                message=f"YAML syntax error in README.md front-matter: {exc}",
                severity="error",
            )
        )
        return None, issues


def _validate_frontmatter(fm: dict[str, Any]) -> list[ValidationIssue]:
    """Validate semantic rules on README frontmatter."""
    issues: list[ValidationIssue] = []

    # Title
    title = fm.get("title")
    if not isinstance(title, str) or len(title.strip()) < 5:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="title",
                message="Dataset 'title' must be a string with at least 5 characters.",
            )
        )

    # Domain
    domain = fm.get("domain")
    if not isinstance(domain, str) or domain.strip().lower() not in VALID_DOMAINS:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="domain",
                message=f"Invalid domain '{domain}'. Permitted: {sorted(VALID_DOMAINS)}",
            )
        )

    # Countries
    countries = fm.get("countries")
    if not isinstance(countries, list) or not countries:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="countries",
                message="'countries' must be a non-empty list of ISO-3166-1 alpha-2 country codes.",
            )
        )
    else:
        for c in countries:
            if not isinstance(c, str) or c.strip().upper() not in AU_COUNTRY_CODES:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column="countries",
                        message=(f"Country code '{c}' is not an African Union member state."),
                    )
                )

    # Taxon IDs
    taxon_ids = fm.get("taxon_ids")
    if not isinstance(taxon_ids, list) or not taxon_ids:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="taxon_ids",
                message="'taxon_ids' must be a non-empty list of NCBI Taxonomy IDs.",
            )
        )
    else:
        for t in taxon_ids:
            if not isinstance(t, int) or t <= 0:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column="taxon_ids",
                        message=f"Taxon ID must be a positive integer, got '{t}'.",
                    )
                )
            elif t in PROHIBITED_TAXA:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column="taxon_ids",
                        message=(f"Human genomic data (Taxon ID {t}) is prohibited in v1."),
                    )
                )

    # License and access
    lic = str(fm.get("license", "")).strip().lower()
    access = str(fm.get("access", "public")).strip().lower()
    if lic in ("custom", "custom-dua", "dua") and access == "public":
        issues.append(
            ValidationIssue(
                file="README.md",
                column="license",
                message="Datasets with custom Data Use Agreements (DUA) must use 'gated' access.",
            )
        )

    return issues


def _validate_sequencing_block(seq: dict[str, Any]) -> list[ValidationIssue]:
    """Validate sequencing experiment configuration and library mappings."""
    issues: list[ValidationIssue] = []

    platform = str(seq.get("platform", "")).strip().upper()
    if platform not in VALID_PLATFORMS:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="sequencing.platform",
                message=f"Invalid platform '{platform}'. Permitted: {sorted(VALID_PLATFORMS)}",
            )
        )

    strategy = str(seq.get("library_strategy", "")).strip().upper()
    if strategy not in VALID_STRATEGIES:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="sequencing.library_strategy",
                message=(
                    f"Invalid library_strategy '{strategy}'. Permitted: {sorted(VALID_STRATEGIES)}"
                ),
            )
        )

    layout = str(seq.get("library_layout", "")).strip().lower()
    if layout not in VALID_LAYOUTS:
        issues.append(
            ValidationIssue(
                file="README.md",
                column="sequencing.library_layout",
                message=f"Invalid library_layout '{layout}'. Permitted: {sorted(VALID_LAYOUTS)}",
            )
        )

    nominal_len = seq.get("nominal_length")
    if layout == "paired" and (not isinstance(nominal_len, int) or nominal_len <= 0):
        issues.append(
            ValidationIssue(
                file="README.md",
                column="sequencing.nominal_length",
                message=(
                    "nominal_length must be a positive integer when library_layout is 'paired'."
                ),
            )
        )

    libraries = seq.get("libraries")
    if libraries is not None and not isinstance(libraries, list):
        issues.append(
            ValidationIssue(
                file="README.md",
                column="sequencing.libraries",
                message="'libraries' must be a list of library mappings.",
            )
        )
    elif isinstance(libraries, list):
        lib_ids: set[str] = set()
        for idx, lib in enumerate(libraries):
            if not isinstance(lib, dict):
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{idx}]",
                        message="Library entry must be a dictionary.",
                    )
                )
                continue

            lib_id = str(lib.get("library_id", "")).strip()
            if not lib_id:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{idx}].library_id",
                        message="Missing 'library_id' in library definition.",
                    )
                )
            elif lib_id in lib_ids:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{idx}].library_id",
                        message=f"Duplicate library_id '{lib_id}' found.",
                    )
                )
            lib_ids.add(lib_id)

            sample_name = str(lib.get("sample_name", "")).strip()
            if not sample_name:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{lib_id}].sample_name",
                        message="Missing 'sample_name' in library definition.",
                    )
                )

            file_type = str(lib.get("file_type", "")).strip().upper()
            if file_type not in VALID_FILE_TYPES:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{lib_id}].file_type",
                        message=(
                            f"Invalid file_type '{file_type}'. "
                            f"Permitted: {sorted(VALID_FILE_TYPES)}"
                        ),
                    )
                )

            filenames = lib.get("filenames")
            if not isinstance(filenames, list) or not filenames:
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{lib_id}].filenames",
                        message="Library must specify a non-empty list of 'filenames'.",
                    )
                )
            else:
                if layout == "paired" and len(filenames) != 2:
                    issues.append(
                        ValidationIssue(
                            file="README.md",
                            column=f"sequencing.libraries[{lib_id}].filenames",
                            message=(
                                f"Library '{lib_id}' layout is 'paired' but specifies "
                                f"{len(filenames)} filenames. Exactly 2 filenames are required."
                            ),
                        )
                    )
                elif layout == "single" and len(filenames) != 1:
                    issues.append(
                        ValidationIssue(
                            file="README.md",
                            column=f"sequencing.libraries[{lib_id}].filenames",
                            message=(
                                f"Library '{lib_id}' layout is 'single' but specifies "
                                f"{len(filenames)} filenames. Exactly 1 filename is required."
                            ),
                        )
                    )

                for fn in filenames:
                    fn_str = str(fn).strip()
                    if fn_str.startswith("/") or ".." in fn_str.split("/"):
                        issues.append(
                            ValidationIssue(
                                file="README.md",
                                column=f"sequencing.libraries[{lib_id}].filenames",
                                message=(f"Path traversal or absolute paths not permitted: '{fn}'"),
                            )
                        )

    return issues


def validate_local_dataset(folder_path: Path) -> ValidationResult:
    """Perform comprehensive pre-flight verification on a local dataset folder.

    Validates:
    - README.md front-matter schema and sequencing libraries
    - samples.tsv MIxS compliance and African sovereignty rules
    - remote_files.tsv URLs and MD5 checksums
    - Two-way parity between declared files, samples, and files on disk.
    """
    logger.debug("Validating local dataset at: %s", folder_path)
    all_issues: list[ValidationIssue] = []

    # 1. Discover local files (relative paths)
    discovered_files: set[str] = set()
    try:
        for p in folder_path.rglob("*"):
            if p.is_file():
                rel = p.relative_to(folder_path).as_posix()
                parts = set(rel.split("/"))
                if not parts.intersection(DEFAULT_IGNORE_DIRS):
                    discovered_files.add(rel)
    except OSError as exc:
        logger.error("Error scanning directory '%s': %s", folder_path, exc)
        return ValidationResult(
            is_valid=False,
            issues=[
                ValidationIssue(
                    file=str(folder_path),
                    message=f"Could not read directory files: {exc}",
                    severity="error",
                )
            ],
        )

    # 2. Check README.md
    readme_path = folder_path / "README.md"
    frontmatter: dict[str, Any] | None = None
    if not readme_path.exists():
        all_issues.append(
            ValidationIssue(
                file="README.md",
                message="Missing mandatory file 'README.md'.",
                severity="error",
            )
        )
    else:
        try:
            readme_text = readme_path.read_text(encoding="utf-8")
            fm, fm_issues = _extract_frontmatter(readme_text)
            all_issues.extend(fm_issues)
            if fm is not None:
                frontmatter = fm
                all_issues.extend(_validate_frontmatter(fm))
                seq = fm.get("sequencing")
                if seq is not None and isinstance(seq, dict):
                    all_issues.extend(_validate_sequencing_block(seq))
        except (OSError, UnicodeDecodeError) as exc:
            logger.error("Failed to read README.md: %s", exc)
            all_issues.append(
                ValidationIssue(
                    file="README.md",
                    message=f"Failed to read README.md: {exc}",
                    severity="error",
                )
            )

    # 3. Check samples.tsv
    samples_path = folder_path / "samples.tsv"
    sample_ids: set[str] = set()
    sample_count = 0
    if not samples_path.exists():
        all_issues.append(
            ValidationIssue(
                file="samples.tsv",
                message="Missing mandatory file 'samples.tsv'.",
                severity="error",
            )
        )
    else:
        try:
            samples_text = samples_path.read_text(encoding="utf-8")
            reader = csv.reader(samples_text.splitlines(), delimiter="\t")
            header = next(reader, None)

            if header is None:
                all_issues.append(
                    ValidationIssue(
                        file="samples.tsv",
                        line=1,
                        message="samples.tsv is empty; header row required.",
                    )
                )
            else:
                cleaned_header = [c.strip() for c in header]
                col_idx = {c: i for i, c in enumerate(cleaned_header)}
                missing_cols = [c for c in MANDATORY_SAMPLE_COLUMNS if c not in cleaned_header]
                if missing_cols:
                    all_issues.append(
                        ValidationIssue(
                            file="samples.tsv",
                            line=1,
                            message=f"samples.tsv is missing mandatory columns: {missing_cols}",
                        )
                    )

                card_countries = (
                    set(frontmatter.get("countries", []))
                    if frontmatter and isinstance(frontmatter.get("countries"), list)
                    else None
                )

                for line_num, row in enumerate(reader, start=2):
                    if not row or all(not cell.strip() for cell in row):
                        continue
                    sample_count += 1

                    if "sample_id" in col_idx:
                        sid = (
                            row[col_idx["sample_id"]].strip()
                            if col_idx["sample_id"] < len(row)
                            else ""
                        )
                        if not sid:
                            all_issues.append(
                                ValidationIssue(
                                    file="samples.tsv",
                                    line=line_num,
                                    column="sample_id",
                                    message="Empty sample_id encountered.",
                                )
                            )
                        elif sid in sample_ids:
                            all_issues.append(
                                ValidationIssue(
                                    file="samples.tsv",
                                    line=line_num,
                                    column="sample_id",
                                    message=f"Duplicate sample_id '{sid}' encountered.",
                                )
                            )
                        sample_ids.add(sid)

                    # Country check
                    if "country" in col_idx:
                        c_code = (
                            row[col_idx["country"]].strip().upper()
                            if col_idx["country"] < len(row)
                            else ""
                        )
                        if c_code not in AU_COUNTRY_CODES:
                            all_issues.append(
                                ValidationIssue(
                                    file="samples.tsv",
                                    line=line_num,
                                    column="country",
                                    message=(
                                        f"Sample country '{c_code}' is not an AU member state."
                                    ),
                                )
                            )
                        elif card_countries is not None and c_code not in card_countries:
                            all_issues.append(
                                ValidationIssue(
                                    file="samples.tsv",
                                    line=line_num,
                                    column="country",
                                    message=(
                                        f"Sample country '{c_code}' is not declared in README "
                                        f"countries: {sorted(card_countries)}"
                                    ),
                                )
                            )

                    # Taxon check
                    if "taxon_id" in col_idx:
                        tax_raw = (
                            row[col_idx["taxon_id"]].strip()
                            if col_idx["taxon_id"] < len(row)
                            else ""
                        )
                        try:
                            tax_int = int(tax_raw)
                            if tax_int in PROHIBITED_TAXA:
                                all_issues.append(
                                    ValidationIssue(
                                        file="samples.tsv",
                                        line=line_num,
                                        column="taxon_id",
                                        message=(
                                            f"samples.tsv row {line_num}: "
                                            f"Human data (Taxon ID {tax_int}) is prohibited in v1."
                                        ),
                                    )
                                )
                        except ValueError:
                            all_issues.append(
                                ValidationIssue(
                                    file="samples.tsv",
                                    line=line_num,
                                    column="taxon_id",
                                    message=f"Invalid taxon_id '{tax_raw}'; must be an integer.",
                                )
                            )

                    # Date check
                    if "collection_date" in col_idx:
                        date_raw = (
                            row[col_idx["collection_date"]].strip()
                            if col_idx["collection_date"] < len(row)
                            else ""
                        )
                        if not DATE_REGEX.match(date_raw):
                            all_issues.append(
                                ValidationIssue(
                                    file="samples.tsv",
                                    line=line_num,
                                    column="collection_date",
                                    message=(
                                        f"Invalid collection_date '{date_raw}'. "
                                        "Expected ISO-8601 (YYYY, YYYY-MM, YYYY-MM-DD)."
                                    ),
                                )
                            )

                    # Geolocation check
                    if "lat" in col_idx and "lon" in col_idx:
                        lat_raw = row[col_idx["lat"]].strip() if col_idx["lat"] < len(row) else ""
                        lon_raw = row[col_idx["lon"]].strip() if col_idx["lon"] < len(row) else ""
                        if lat_raw and lon_raw:
                            try:
                                lat_f = float(lat_raw)
                                lon_f = float(lon_raw)
                                if not (AFRICA_LAT_MIN <= lat_f <= AFRICA_LAT_MAX):
                                    all_issues.append(
                                        ValidationIssue(
                                            file="samples.tsv",
                                            line=line_num,
                                            column="lat",
                                            message=(
                                                f"Latitude {lat_f} is outside African bounds "
                                                f"[{AFRICA_LAT_MIN}, {AFRICA_LAT_MAX}]."
                                            ),
                                        )
                                    )
                                if not (AFRICA_LON_MIN <= lon_f <= AFRICA_LON_MAX):
                                    all_issues.append(
                                        ValidationIssue(
                                            file="samples.tsv",
                                            line=line_num,
                                            column="lon",
                                            message=(
                                                f"Longitude {lon_f} is outside African bounds "
                                                f"[{AFRICA_LON_MIN}, {AFRICA_LON_MAX}]."
                                            ),
                                        )
                                    )
                            except ValueError:
                                all_issues.append(
                                    ValidationIssue(
                                        file="samples.tsv",
                                        line=line_num,
                                        column="lat/lon",
                                        message="lat/lon values must be decimal floats.",
                                    )
                                )
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            logger.error("Failed to read samples.tsv: %s", exc)
            all_issues.append(
                ValidationIssue(
                    file="samples.tsv",
                    message=f"Failed to read samples.tsv: {exc}",
                )
            )

    # 4. Check remote_files.tsv (optional)
    remote_path = folder_path / "remote_files.tsv"
    remote_filenames: set[str] = set()
    remote_file_count = 0
    if remote_path.exists():
        try:
            remote_text = remote_path.read_text(encoding="utf-8")
            reader = csv.reader(remote_text.splitlines(), delimiter="\t")
            for line_num, row in enumerate(reader, start=1):
                if not row or row[0].startswith("#") or all(not c.strip() for c in row):
                    continue
                if row[0].strip().lower() == "filename":
                    continue
                if len(row) < 4:
                    continue
                remote_file_count += 1
                fn = row[0].strip()
                url = row[1].strip()
                md5 = row[2].strip()
                size_str = row[3].strip()

                remote_filenames.add(fn)

                if not (
                    url.startswith("https://")
                    or url.startswith("ftp://")
                    or url.startswith("http://")
                ):
                    all_issues.append(
                        ValidationIssue(
                            file="remote_files.tsv",
                            line=line_num,
                            column="url",
                            message=f"URL must start with https:// or ftp://. Got '{url}'.",
                        )
                    )
                if not MD5_REGEX.match(md5):
                    all_issues.append(
                        ValidationIssue(
                            file="remote_files.tsv",
                            line=line_num,
                            column="md5",
                            message=(
                                f"Invalid MD5 hash '{md5}'. "
                                "Expected 32-character hexadecimal string."
                            ),
                        )
                    )
                try:
                    sz = int(size_str)
                    if sz <= 0:
                        all_issues.append(
                            ValidationIssue(
                                file="remote_files.tsv",
                                line=line_num,
                                column="size_bytes",
                                message="size_bytes must be a positive integer.",
                            )
                        )
                except ValueError:
                    all_issues.append(
                        ValidationIssue(
                            file="remote_files.tsv",
                            line=line_num,
                            column="size_bytes",
                            message=f"size_bytes must be an integer, got '{size_str}'.",
                        )
                    )
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            logger.error("Failed to read remote_files.tsv: %s", exc)
            all_issues.append(
                ValidationIssue(
                    file="remote_files.tsv",
                    message=f"Failed to read remote_files.tsv: {exc}",
                )
            )

    # 5. Two-Way Parity and Sequencing Library Verification
    library_count = 0
    declared_sequence_files: set[str] = set()
    sniff_results: list[Any] = []
    sniffed_files: set[str] = set()

    if frontmatter is not None:
        seq_block = frontmatter.get("sequencing")
        if isinstance(seq_block, dict):
            libs = seq_block.get("libraries")
            if isinstance(libs, list):
                library_count = len(libs)
                for lib in libs:
                    if not isinstance(lib, dict):
                        continue
                    lib_id = str(lib.get("library_id", "")).strip()
                    sample_name = str(lib.get("sample_name", "")).strip()

                    # Check sample linkage
                    if samples_path.exists() and sample_name and sample_name not in sample_ids:
                        all_issues.append(
                            ValidationIssue(
                                file="README.md",
                                column=f"sequencing.libraries[{lib_id}].sample_name",
                                message=(
                                    f"Library '{lib_id}' references sample_name '{sample_name}', "
                                    f"which does not exist in samples.tsv."
                                ),
                            )
                        )

                    # Check declared files
                    fns = lib.get("filenames")
                    if isinstance(fns, list):
                        for fn in fns:
                            fn_clean = str(fn).strip()
                            declared_sequence_files.add(fn_clean)
                            if (
                                fn_clean not in discovered_files
                                and fn_clean not in remote_filenames
                            ):
                                all_issues.append(
                                    ValidationIssue(
                                        file="README.md",
                                        column=f"sequencing.libraries[{lib_id}].filenames",
                                        message=(
                                            f"Missing declared sequence file '{fn_clean}' for "
                                            f"library '{lib_id}'. File was not found on disk "
                                            "or remote_files.tsv."
                                        ),
                                    )
                                )
                            elif fn_clean in discovered_files and fn_clean not in sniffed_files:
                                sniffed_files.add(fn_clean)
                                from ubuntu_bio.sniffer import sniff_sequence_file

                                seq_path = folder_path / fn_clean
                                sniff_res = sniff_sequence_file(seq_path)
                                sniff_results.append(sniff_res)
                                for issue in sniff_res.issues:
                                    all_issues.append(issue)

            # Orphan check: look for sequence files on disk not declared
            for p_rel in discovered_files:
                p_lower = p_rel.lower()
                if (
                    any(p_lower.endswith(ext) for ext in SEQUENCE_FILE_EXTENSIONS)
                    and p_rel not in declared_sequence_files
                    and p_rel not in remote_filenames
                ):
                    all_issues.append(
                        ValidationIssue(
                            file=p_rel,
                            message=(
                                f"Orphaned sequence file '{p_rel}'. File exists on disk but is "
                                "not declared in README.md sequencing libraries or "
                                "remote_files.tsv."
                            ),
                        )
                    )

    has_errors = any(i.severity == "error" for i in all_issues)
    logger.info(
        "Validation completed for '%s': valid=%s, errors=%d, warnings=%d",
        folder_path,
        not has_errors,
        len([i for i in all_issues if i.severity == "error"]),
        len([i for i in all_issues if i.severity == "warning"]),
    )

    return ValidationResult(
        is_valid=not has_errors,
        issues=all_issues,
        sample_count=sample_count,
        remote_file_count=remote_file_count,
        library_count=library_count,
        sniff_results=sniff_results,
    )
