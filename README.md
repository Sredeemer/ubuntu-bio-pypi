# ubuntu-bio-pypi

Official Python client and command-line interface (`ubuntu-bio`) for **UbuntuBio** — the African Bioinformatics Data Hub.

`ubuntu-bio` allows researchers to publish, discover, stream, and download African bioinformatics datasets (bacteria, viruses, veterinary/One Health, plant pathogens, parasites, and metagenomics) with chunk-level deduplication and Git versioning.

---

## Installation

```bash
pip install ubuntu-bio
```

Or with `uv`:

```bash
uv add ubuntu-bio
```

---

## Quickstart

### 1. Authenticate with ORCID

```bash
ubio login
```

Or in Python:

```python
import ubuntu_bio as ub

ub.login(token="ubp_your_personal_access_token")
print(ub.whoami())
```

### 2. Download Datasets & Snapshots

```python
import ubuntu_bio as ub

# Download a single file from a repository
fasta_path = ub.download_file("pasteur-dakar/lassa-isolate-2023", "assemblies/isolate_01.fasta")

# Download the complete repository snapshot
dataset_dir = ub.snapshot_download("pasteur-dakar/lassa-isolate-2023", revision="main")
```

### 3. Publish & Push Data

```python
import ubuntu_bio as ub

# Create a new repository
ub.create_repo(
    repo_id="pasteur-dakar/lassa-isolate-2023",
    domain="virus",
    access="public",
    description="Lassa virus surveillance in Senegal",
)

# Upload an entire folder
ub.upload_folder(
    repo_id="pasteur-dakar/lassa-isolate-2023",
    folder_path="./data",
    message="Add Lassa virus isolate sequences and samples metadata",
)
```

---

## CLI Usage

The package installs two identical CLI entrypoints: `ubio` and `ubuntu-bio`.

```bash
# Check current authenticated user
ubio whoami

# Create a repository
ubio create pasteur-dakar/lassa-2024 --domain virus --access public

# Upload a dataset folder
ubio upload pasteur-dakar/lassa-2024 ./my-dataset --message "Initial release"

# Download a dataset snapshot
ubio download pasteur-dakar/lassa-2024 --output-dir ./local-data

# Download external files from a remote_files.tsv with MD5 verification
ubio download-remote ./remote_files.tsv --output-dir ./downloads

# Search public datasets
ubio search "cholera" --country "KE"
```
