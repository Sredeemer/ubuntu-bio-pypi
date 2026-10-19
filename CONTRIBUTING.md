# Contributing to ubuntu-bio

Welcome to **ubuntu-bio**! We are building open-source data infrastructure for African bioinformatics, enabling researchers and public health institutes to publish, version, discover, and stream genomic datasets.

Whether you are fixing a typo in documentation, improving metadata validation, adding CLI ergonomics, or writing tests, thank you for contributing!

---

## Ways to Contribute

Code is not the only way to help the community:
- **Reporting Bugs & Issues**: Open an issue describing the unexpected behavior, steps to reproduce, and your OS/Python version.
- **Requesting Features**: Share ideas for new commands, integrations with bioinformatics workflows (e.g. Nextflow, Snakemake), or performance improvements.
- **Improving Documentation**: Fix typos, add examples, or expand guides.
- **Answering Questions**: Help others in GitHub Discussions or Issues.

---

## Development Setup

The project uses [`uv`](https://docs.astral.sh/uv/) for fast, deterministic dependency management.

### 1. Clone the Repository

```bash
git clone https://github.com/Sredeemer/ubuntu-bio-pypi.git
cd ubuntu-bio-pypi
```

### 2. Install Development Dependencies

```bash
uv sync --all-extras
```

### 3. Verify Local Environment

Run the full verification suite:

```bash
# Run test suite
uv run pytest

# Check types with strict Mypy
uv run mypy src tests

# Run Ruff linter and formatter checks
uv run ruff check .
uv run ruff format --check .
```

---

## Code Style & Standards

- **Python Version**: Python 3.12+.
- **Type Annotations**: Strict static typing everywhere (`strict = true` in mypy). Avoid `Any` where possible.
- **Linting & Formatting**: Enforced via `ruff`. Run `uv run ruff format .` and `uv run ruff check --fix .` before committing.
- **Testing**: Every new feature or bug fix must have unit tests in `tests/`.
- **Domain Invariants**:
  - Human genomic data (NCBI Taxon ID 9606) is strictly prohibited in v1.
  - African country codes must adhere to the 54 African Union ISO-3166-1 alpha-2 codes.

---

## Pull Request Workflow

1. **Create a branch**:
   ```bash
   git checkout -b feat/my-new-feature
   ```
2. **Follow Conventional Commits**:
   - `feat(cli): add --json output flag to whoami`
   - `fix(auth): handle loopback timeout gracefully`
   - `docs(readme): add example for snapshot download`
   - `test(upload): add mock tests for chunked upload`
3. **Push and Open a Pull Request**:
   Once pushed, GitHub Actions will automatically run the CI suite to verify your changes.
