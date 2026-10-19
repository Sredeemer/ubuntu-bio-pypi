# ubuntu-bio

[![PyPI version](https://img.shields.io/pypi/v/ubuntu-bio.svg?color=blue)](https://pypi.org/project/ubuntu-bio/)
[![Python versions](https://img.shields.io/pypi/pyversions/ubuntu-bio.svg)](https://pypi.org/project/ubuntu-bio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/Sredeemer/ubuntu-bio-pypi/actions/workflows/ci.yml/badge.svg)](https://github.com/Sredeemer/ubuntu-bio-pypi/actions/workflows/ci.yml)

The official Python client and command-line interface (`ubio`) for **UbuntuBio** — the African Bioinformatics Data Hub.

`ubuntu-bio` enables researchers across the African continent and globally to publish, discover, stream, and version bioinformatics datasets (pathogen genomics, AMR surveillance, agriculture, biodiversity, and metagenomics) with chunk-level deduplication and Git versioning.

---

## Key Features

- **Researcher Identity & Namespaces**: Seamless ORCID-authenticated login via browser loopback or RFC 8628 device flow with personal namespace resolution (`@username/dataset-name`).
- **Genomic Deduplication**: Powered by OpenXet Content-Addressed Storage (CAS) using 64 KiB Content-Defined Chunking (CDC) and Blake3 Merkle trees—identical sequence chunks are stored only once.
- **Git Versioning**: Every dataset is backed by standard Git commit histories, tags, and branches.
- **Metadata Standards & Data Governance**: Built-in MIxS checklist validation and African Union ISO-3166 country code verification. Non-human genomics strictly enforced in v1.
- **Dual Interface**: Full-featured command-line interface (`ubio` or `ubuntu-bio`) and ergonomic Python SDK (`import ubuntu_bio as ub`).

---

## Installation

Install using `pip`:

```bash
pip install ubuntu-bio
```

Or using `uv`:

```bash
uv add ubuntu-bio
```

---

## CLI Quickstart

The package installs two identical CLI entrypoints: `ubio` and `ubuntu-bio`.

### 1. Authenticate with ORCID
Connect your ORCID iD. Opens an interactive browser authorization or falls back to an RFC 8628 device verification code:

```bash
ubio login
```

Verify your authenticated researcher profile:

```bash
ubio whoami
```

```text
✓ Authenticated with UbuntuBio Hub
  Name:       Dr. Ada Lovelace
  Username:   @ada-lovelace
  ORCID:      0000-0002-1825-0097
  Role:       researcher
  Server:     https://hub.ubuntubio.org
```

### 2. Create a Dataset Repository
Create a new dataset repository. If you provide a bare slug, `ubio` automatically prefixes your verified researcher handle:

```bash
# Automatically creates @ada-lovelace/lassa-surveillance-2024
ubio create lassa-surveillance-2024 --domain virus --access public

# Or specify an institutional / organization namespace
ubio create pasteur-dakar/lassa-2024 --domain virus --access public
```

Supported biological domains:
`bacteria`, `virus`, `parasite`, `fungus`, `plant`, `animal`, `vector`, `metagenome`, `environmental`.

### 3. Upload Datasets
Upload an entire directory of sequences, alignments, and metadata:

```bash
ubio upload lassa-surveillance-2024 ./my-data --message "Initial release of Lineage II FASTA assemblies"
```

### 4. Search Public Datasets
Search the catalog using full-text search across pathogen titles, descriptions, and AU member states:

```bash
# Search for cholera surveillance in Kenya
ubio search "cholera" --country KE

# Search for antimicrobial resistance studies
ubio search "antimicrobial resistance" --domain bacteria
```

### 5. Download Datasets & Remote Files
Download a snapshot of a dataset repository:

```bash
ubio download lassa-surveillance-2024 --output-dir ./local-data
```

Download external assets listed in a `remote_files.tsv` manifest with parallel MD5 verification:

```bash
ubio download-remote ./remote_files.tsv --output-dir ./downloads --workers 8
```

---

## Python SDK Quickstart

Use `ubuntu_bio` directly in your Python analysis pipelines and Jupyter notebooks:

```python
import ubuntu_bio as ub

# 1. Authenticate (using a Personal Access Token or environment variable)
ub.login(token="ubp_your_personal_access_token")

# 2. Check profile
profile = ub.whoami()
print(f"Logged in as: @{profile.get('username')}")

# 3. Create a repository
repo = ub.create_repo(
    repo_id="lassa-surveillance-2024",
    domain="virus",
    access="public",
    description="Lassa virus genomic surveillance in West Africa",
)

# 4. Upload an entire folder of genomic files
ub.upload_folder(
    repo_id="lassa-surveillance-2024",
    folder_path="./data",
    message="Add consensus FASTA and GFF annotations",
)

# 5. Download a single file or complete snapshot
fasta_path = ub.download_file("pasteur-dakar/cholera-2024", "assemblies/sample_01.fasta")
dataset_dir = ub.snapshot_download("pasteur-dakar/cholera-2024", revision="main")
```

---

## Configuration & Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `UBUNTUBIO_SERVER_URL` | UbuntuBio Hub API server URL | `https://hub.ubuntubio.org` |
| `UBUNTUBIO_API_TOKEN` | Personal Access Token (`ubp_...`) for non-interactive environments / CI | `None` |
| `UBUNTUBIO_CONFIG_DIR` | Directory storing local credentials cache | `~/.config/ubuntubio` |

---

## Security & Biological Data Ethics

- **Non-Human Data Only**: In compliance with UbuntuBio v1 data governance rules, human genomic data (NCBI Taxon ID 9606) is strictly prohibited.
- **African Union Member States**: Metadata validation strictly enforces the 54 AU member state ISO-3166-1 alpha-2 country codes.
- **Token Security**: Tokens are stored locally with restrictive file permissions (`0600`) and validated via short-lived cryptographic tokens against the Hub.

---

## License

Distributed under the [MIT License](LICENSE).
