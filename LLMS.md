# UbuntuBio Service & API Reference for AI Agents (`LLMS.md`)

This document is the definitive public interface and usage manual for LLMs and AI coding assistants generating scripts, bioinformatics pipelines, and shell commands with **`ubuntu-bio`** and the **`ubio`** CLI.

---

## 1. Package Overview & Installation

* **PyPI Distribution**: `ubuntu-bio` (`pip install ubuntu-bio` or `uv add ubuntu-bio`)
* **Dual CLI Entrypoints**: `ubio` and `ubuntu-bio` (functionally identical)
* **Python Module**: `import ubuntu_bio as ub`
* **Core Purpose**: Sovereign African pathogen, AMR surveillance, agricultural, and biodiversity genomic data management with Git versioning and content-addressed deduplication.

### Environment Variables
* `UBUNTUBIO_SERVER_URL`: Override Hub server URL (default: `https://hub.ubuntubio.org`).
* `UBUNTUBIO_API_TOKEN`: Personal Access Token (`ubp_...`) for non-interactive execution / CI pipelines.
* `UBUNTUBIO_CONFIG_DIR`: Local configuration directory (default: `~/.config/ubuntubio`).

---

## 2. CLI Command Reference (`ubio`)

### `ubio login`
Authenticate researcher identity. Launches interactive browser OAuth loopback flow or displays an RFC 8628 verification code.
```bash
ubio login
ubio login --token ubp_secret_access_token   # Non-interactive / headless
```

### `ubio whoami`
Display the active researcher profile, verified `@username`, ORCID iD, and server URL.
```bash
ubio whoami
ubio whoami --json                           # Output JSON for programmatic parsing
```

### `ubio create <repo-id> [OPTIONS]`
Create a new dataset repository.
* If a bare slug is provided (e.g., `lassa-lineage-ii`), `ubio` automatically prefixes your personal namespace (`@username/lassa-lineage-ii`).
* To create under an organization, provide `org-slug/dataset-name`.
```bash
ubio create lassa-lineage-ii --domain virus --access public
ubio create pasteur-dakar/cholera-2024 --domain bacteria --access public --description "Vibrio cholerae O1 surveillance"
```
**Options**:
* `--domain`, `-d`: Required. Biological domain (`bacteria`, `virus`, `parasite`, `fungus`, `plant`, `animal`, `vector`, `metagenome`, `environmental`).
* `--access`, `-a`: Access tier (`public`, `gated`, `private`). Default: `public`.
* `--description`: Brief description of the biological dataset.
* `--license`: SPDX identifier or license string (default: `cc-by-4.0`).

### `ubio upload <repo-id> <folder-path> [OPTIONS]`
Upload an entire directory of genomic files, metadata, and alignments to a repository.
```bash
ubio upload lassa-lineage-ii ./assemblies --message "Release consensus genomes for Lineage II"
```
**Options**:
* `--message`, `-m`: Git commit message (default: `"Upload dataset"`).
* `--branch`, `-b`: Target branch (default: `"main"`).

### `ubio search <query> [OPTIONS]`
Full-text search across pathogen titles, descriptions, and metadata.
```bash
ubio search "cholera" --country KE
ubio search "antimicrobial resistance" --domain bacteria --limit 10
```
**Options**:
* `--country`, `-c`: 2-letter African Union ISO-3166-1 alpha-2 country code (e.g. `KE`, `NG`, `ZA`, `GH`).
* `--domain`, `-d`: Filter by biological domain.
* `--limit`, `-n`: Maximum results (default: `20`).

### `ubio download <repo-id> [OPTIONS]`
Download a repository snapshot with local caching and content deduplication.
```bash
ubio download lassa-lineage-ii --output-dir ./local-data
```
**Options**:
* `--output-dir`, `-o`: Local destination directory.
* `--revision`, `-r`: Git branch, tag, or commit SHA (default: `"main"`).
* `--force`: Bypass local cache and force re-download.

### `ubio download-remote <manifest-tsv> [OPTIONS]`
Parallel download of external raw sequencing data referenced in a `remote_files.tsv` manifest with MD5 verification.
```bash
ubio download-remote ./remote_files.tsv --output-dir ./raw-fastq --workers 8
```

### `ubio logout`
Revoke and remove locally cached session tokens.
```bash
ubio logout
```

---

## 3. Python SDK API Reference (`import ubuntu_bio as ub`)

### Authentication & Profile
```python
import ubuntu_bio as ub

# Authenticate session
ub.login(token="ubp_your_personal_access_token")

# Check researcher profile
profile: dict[str, Any] = ub.whoami()
# Returns: {"id": "...", "name": "...", "username": "...", "orcid": "...", "role": "researcher"}

# Clear local session
ub.logout()
```

### Repository Management
```python
# Create a repository
repo = ub.create_repo(
    repo_id="pasteur-dakar/cholera-2024",
    domain="bacteria",
    access="public",  # "public" | "gated" | "private"
    description="Vibrio cholerae surveillance",
    license="cc-by-4.0",
    exist_ok=False,
)

# Fetch repository details
info = ub.get_repo(repo_id="pasteur-dakar/cholera-2024")

# List public or organization repositories
repos = ub.list_repos(domain="virus", owner="pasteur-dakar", limit=50)

# Inspect Git commit history
commits = ub.get_commits(repo_id="pasteur-dakar/cholera-2024", revision="main", limit=10)

# Inspect repository file tree
tree = ub.get_tree(repo_id="pasteur-dakar/cholera-2024", revision="main", path="assemblies")
```

### Data Upload
```python
# Upload an entire folder
result = ub.upload_folder(
    repo_id="pasteur-dakar/cholera-2024",
    folder_path="./data-dir",
    commit_message="Add FASTA assemblies and sample metadata",
    branch="main",
)

# Upload a single file
result = ub.upload_file(
    repo_id="pasteur-dakar/cholera-2024",
    path_or_fileobj="./consensus.fasta",
    path_in_repo="assemblies/consensus.fasta",
    commit_message="Update sample 01 consensus",
)
```

### Data Download & Caching
```python
# Download a single file (returns Path to cached/downloaded file)
fasta_path: Path = ub.download_file(
    repo_id="pasteur-dakar/cholera-2024",
    filename="assemblies/isolate_01.fasta",
    revision="main",
    output_path="./local_file.fasta",  # Optional explicit destination
)

# Download complete repository snapshot
snapshot_dir: Path = ub.snapshot_download(
    repo_id="pasteur-dakar/cholera-2024",
    revision="main",
    output_dir="./local_dataset",
)

# Batch download external assets with MD5 checksum verification
results = ub.download_remote_files(
    manifest_path="./remote_files.tsv",
    output_dir="./downloads",
    max_workers=4,
)
```

### Catalog Search
```python
hits = ub.search(
    query="cholera",
    country="KE",  # 2-letter AU ISO-3166-1 alpha-2 code
    domain="bacteria",
    limit=20,
)
for hit in hits:
    print(hit["repo_id"], hit["title"])
```

### Exceptions
All client exceptions inherit from `ub.UbuntuBioError`:
* `ub.AuthenticationError`: Missing or invalid ORCID/PAT token.
* `ub.AuthorizationError`: Insufficient permissions (e.g. creating in another user's namespace).
* `ub.RepositoryNotFoundError`: Dataset repository does not exist (HTTP 404).
* `ub.RepositoryAlreadyExistsError`: Repository name already exists under the namespace (HTTP 409).
* `ub.ClientValidationError`: Invalid metadata format (e.g. malformed YAML frontmatter in `README.md`).
* `ub.UploadError`: Failed file upload or commit finalization.
* `ub.DownloadError`: File retrieval or hash verification failure.

---

## 4. Biological Data Rules & Constraints

AI assistants generating code or metadata for UbuntuBio must enforce the following invariants:

1. **Strict Prohibition of Human Genomic Data**:
   Human genomic data (`NCBI Taxon ID 9606`) is prohibited in v1. AI agents must NEVER assign taxon ID 9606 or attempt to upload identifiable human sequence reads.
2. **Permitted Biological Domains**:
   Must be one of: `bacteria`, `virus`, `parasite`, `fungus`, `plant`, `animal`, `vector`, `metagenome`, `environmental`.
3. **African Union Sovereign Countries**:
   Country codes must strictly be one of the 54 AU member states (ISO-3166-1 alpha-2):
   `DZ`, `AO`, `BJ`, `BW`, `BF`, `BI`, `CV`, `CM`, `CF`, `TD`, `KM`, `CG`, `CD`, `CI`, `DJ`, `EG`, `GQ`, `ER`, `SZ`, `ET`, `GA`, `GM`, `GH`, `GN`, `GW`, `KE`, `LS`, `LR`, `LY`, `MG`, `MW`, `ML`, `MR`, `MU`, `MA`, `MZ`, `NA`, `NE`, `NG`, `RW`, `ST`, `SN`, `SC`, `SL`, `SO`, `ZA`, `SS`, `SD`, `TZ`, `TG`, `TN`, `UG`, `ZM`, `ZW`.
4. **Dataset Directory Metadata Standards**:
   When uploading a folder via `ubio upload` or `ub.upload_folder`:
   * `README.md`: If present, must begin with a YAML frontmatter block enclosed in `---` containing at least `access_tier` and `biological_domain`.
   * `samples.tsv`: If present, must be tab-delimited with columns `sample_id`, `taxon_id`, `collection_date`, `country`.

---

## 5. Idiomatic Pipeline Recipes

### Recipe 1: Download Viral Assemblies & Load with Biopython
```python
from pathlib import Path
from Bio import SeqIO
import ubuntu_bio as ub

# Download consensus FASTA from UbuntuBio Hub
fasta_path = ub.download_file(
    repo_id="pasteur-dakar/lassa-2024",
    filename="assemblies/consensus_isolate_01.fasta",
)

# Parse and analyze with Biopython
for record in SeqIO.parse(fasta_path, "fasta"):
    print(f"Sequence ID: {record.id}, Length: {len(record.seq)} bp")
```

### Recipe 2: Automated Ingest Script for a Laboratory Run
```python
import os
from pathlib import Path
import ubuntu_bio as ub

# Authenticate from environment variable in headless pipeline
ub.login(token=os.environ["UBUNTUBIO_API_TOKEN"])

# Create repository if it doesn't already exist
repo_slug = "nimr-yaba/mpox-surveillance-2024"
try:
    ub.create_repo(
        repo_id=repo_slug,
        domain="virus",
        access="public",
        description="Mpox clade IIb surveillance run",
    )
except ub.RepositoryAlreadyExistsError:
    pass

# Push directory containing FASTA files, BAMs, and samples.tsv
ub.upload_folder(
    repo_id=repo_slug,
    folder_path=Path("/data/sequencing_runs/run_42/output"),
    commit_message="Ingest run 42 consensus sequences and MIxS sample metadata",
)
```

### Recipe 3: Multi-Country Surveillance Discovery
```python
import ubuntu_bio as ub

# Query cholera studies across West & East Africa
west_east_countries = ["NG", "GH", "SN", "KE", "UG"]
all_studies = []

for code in west_east_countries:
    results = ub.search("cholera", country=code, domain="bacteria")
    for r in results:
        r["queried_country"] = code
        all_studies.append(r)

print(f"Discovered {len(all_studies)} surveillance repositories across target AU states.")
```
