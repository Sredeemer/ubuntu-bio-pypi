"""Command-line interface (CLI) for UbuntuBio (M2-07)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ubuntu_bio import __version__
from ubuntu_bio.auth import (
    LoopbackCallbackServer,
    find_free_port,
    request_device_code,
    wait_for_auth_token,
)
from ubuntu_bio.auth import (
    login as auth_login,
)
from ubuntu_bio.auth import (
    logout as auth_logout,
)
from ubuntu_bio.auth import (
    whoami as auth_whoami,
)
from ubuntu_bio.config import get_hub_url
from ubuntu_bio.download import download_file, download_remote_files, snapshot_download
from ubuntu_bio.exceptions import ClientValidationError, UbuntuBioError
from ubuntu_bio.hub import create_repo as hub_create_repo
from ubuntu_bio.scaffold import init_dataset
from ubuntu_bio.search import search as hub_search
from ubuntu_bio.upload import upload_file, upload_folder
from ubuntu_bio.validator import validate_local_dataset

app = typer.Typer(
    name="ubio",
    help="""[bold #00ed64]UbuntuBio CLI[/bold #00ed64] - African Sovereign Bioinformatics Hub.

[bold white]Workflow & Common Subcommands:[/bold white]
  • [bold #00d2ff]ubio login[/bold #00d2ff]      ORCID browser authentication or token setup.
  • [bold #00d2ff]ubio whoami[/bold #00d2ff]     Inspect verified identity, handle, and AU status.
  • [bold #00d2ff]ubio init[/bold #00d2ff]       Scaffold a MIxS-compliant dataset directory.
  • [bold #00d2ff]ubio check[/bold #00d2ff]      Validate local metadata and verify file parity.
  • [bold #00d2ff]ubio create[/bold #00d2ff]     Create dataset (defaults to personal namespace).
  • [bold #00d2ff]ubio upload[/bold #00d2ff]     Upload files/directories with Git versioning.
  • [bold #00d2ff]ubio download[/bold #00d2ff]   Download specific files or full snapshots.
  • [bold #00d2ff]ubio search[/bold #00d2ff]     Search African pathogen & biodiversity genomics.
  • [bold #00d2ff]ubio download-remote[/bold #00d2ff] Fetch external mirrors from remote_files.tsv.

[bold white]Quick Examples:[/bold white]
  [dim]# 1. Scaffold a new pathogen dataset directory[/dim]
  [green]$[/green] ubio init ./lassa-surveillance-2024

  [dim]# 2. Pre-flight check local dataset before uploading[/dim]
  [green]$[/green] ubio check ./lassa-surveillance-2024

  [dim]# 3. Authenticate with ORCID[/dim]
  [green]$[/green] ubio login

  [dim]# 4. Create and upload dataset[/dim]
  [green]$[/green] ubio create lassa-surveillance-2024 --domain virus
  [green]$[/green] ubio upload lassa-surveillance-2024 ./lassa-surveillance-2024
""",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()


def resolve_repo_slug(repo_id: str, command_name: str = "operation") -> str:
    """Resolve repository slug.

    If a bare repository name is given (e.g., 'lassa-2024' without '/'),
    defaults automatically to the authenticated researcher's personal namespace (@username).
    """
    if "/" in repo_id:
        return repo_id

    try:
        profile = auth_whoami()
        owner = profile.get("username") or profile.get("orcid_id")
        if not owner:
            console.print(
                f"[bold red]Error:[/bold red] Could not determine personal namespace "
                f"to run '{command_name}'.\n"
                "Please specify a fully-qualified repository slug '[cyan]owner/name[/cyan]' "
                "or log in via '[bold #00ed64]ubio login[/bold #00ed64]'."
            )
            raise typer.Exit(code=1)

        target_slug = f"{owner}/{repo_id}"
        console.print(
            f"[dim]Using personal namespace:[/dim] [bold #00ed64]@{owner}[/bold #00ed64] "
            f"→ [cyan]{target_slug}[/cyan]"
        )
        return target_slug
    except UbuntuBioError as exc:
        console.print(
            f"[bold red]Error:[/bold red] Cannot default to personal namespace ({exc}).\n"
            "Please provide a fully-qualified repository slug '[cyan]owner/name[/cyan]' "
            "or log in via '[bold #00ed64]ubio login[/bold #00ed64]'."
        )
        raise typer.Exit(code=1) from exc


def render_ascii_banner() -> Text:
    """Generate two-tone ASCII art banner for UbuntuBio."""
    lines = [
        ("   __  ____                  __         ", "____  _       "),
        ("  / / / / /_  __  ______  __/ /___  __ ", "/ __ )(_)___   "),
        (" / / / / __ \\/ / / / __ \\/ __/ / / / /", "/ __  / / __ \\  "),
        ("/ /_/ / /_/ / /_/ / / / / /_/ /_/ / /", "/ /_/ / / /_/ /  "),
        (r"\____/_.___/\__,_/_/ /_/\__/\__,_/_/", r"/_____/_/\____/   "),
    ]
    t = Text()
    for left, right in lines:
        t.append(left, style="bold #00ed64")
        t.append(right, style="bold #00d2ff")
        t.append("\n")
    return t


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold green]UbuntuBio CLI[/bold green] version: {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show version and exit.", callback=version_callback),
    ] = False,
) -> None:
    """UbuntuBio CLI root."""


@app.command()
def login(
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            "-t",
            help="Personal Access Token (ubp_...).",
        ),
    ] = None,
    manual: Annotated[
        bool,
        typer.Option(
            "--manual",
            "-m",
            help="Manually enter token without opening browser.",
        ),
    ] = False,
    device: Annotated[
        bool,
        typer.Option(
            "--device",
            "-d",
            help="Use standard RFC 8628 device code flow directly.",
        ),
    ] = False,
) -> None:
    """Log in to UbuntuBio Hub via browser (ORCID) or Personal Access Token.

    [bold white]Authentication Methods:[/bold white]
      1. [bold #00d2ff]Browser Login (Default)[/bold #00d2ff]: Opens browser for ORCID.
         Instant loopback handshake completes terminal authorization automatically.
      2. [bold #00d2ff]Device Code Flow (--device)[/bold #00d2ff]: Displays RFC 8628 code
         for headless terminals or remote machines.
      3. [bold #00d2ff]Manual Token (--token / --manual)[/bold #00d2ff]: Provide token (ubp_...).

    [bold white]Examples:[/bold white]
      [dim]# Interactive browser login with ORCID:[/dim]
      [green]$[/green] ubio login

      [dim]# Headless or remote server login:[/dim]
      [green]$[/green] ubio login --device

      [dim]# Supply token directly:[/dim]
      [green]$[/green] ubio login --token ubp_xxxxxxxxxxxxxxxx
    """
    # 1. Manual / explicit token provided
    if token:
        clean_token = token.strip()
    elif manual:
        clean_token = typer.prompt(
            "Enter your UbuntuBio Personal Access Token", hide_input=True
        ).strip()
    else:
        # 2. Interactive Browser-based Dual-Mode Authentication
        loopback_server: LoopbackCallbackServer | None = None
        try:
            hub_base = get_hub_url().rstrip("/")
            # Step A: Request Device Authorization Code from Hub (for fallback)
            code_data = request_device_code()
            user_code = code_data["user_code"]
            device_code = code_data["device_code"]
            verification_url = code_data["verification_uri_complete"]
            interval = code_data.get("interval", 1)
            expires_in = code_data.get("expires_in", 300)

            # Step B: Try starting ephemeral local loopback server for instant handshake
            if not device:
                try:
                    port = find_free_port()
                    server = LoopbackCallbackServer(port=port)
                    server.start()
                    loopback_server = server
                    browser_url = f"{hub_base}/api/auth/orcid/authorize?state=cli_port_{port}"
                except Exception:
                    # In restricted/container environments, gracefully fall back to device code
                    loopback_server = None
                    browser_url = verification_url
            else:
                browser_url = verification_url

            # Build visual panel
            panel_text = render_ascii_banner()
            panel_text.append(
                "\n  🌍 African Sovereign Bioinformatics Data Hub\n",
                style="bold white",
            )
            panel_text.append(
                "  Genomic Intelligence & Pathogen Surveillance across 54 AU Member States\n\n",
                style="dim #9ca3af",
            )
            panel_text.append("  [1] Authorize in Browser:\n", style="bold white")
            panel_text.append(f"      {browser_url}\n\n", style="bold #00d2ff underline")
            panel_text.append("  [2] One-Time Code:        ", style="bold white")
            panel_text.append(f"  {user_code}  \n", style="bold black on #00ed64")

            mode_note = (
                "Instant loopback active" if loopback_server else "RFC 8628 Device Authorization"
            )
            subtitle_str = (
                f"[dim]Opening browser automatically • {mode_note} • "
                "Press Ctrl+C for manual token[/dim]"
            )
            panel = Panel(
                panel_text,
                title="[bold #00ed64]UbuntuBio Terminal Authentication[/bold #00ed64]",
                subtitle=subtitle_str,
                box=box.ROUNDED,
                border_style="#00ed64",
            )
            console.print(panel)

            # Attempt to automatically launch the default browser
            try:
                import webbrowser

                webbrowser.open(browser_url)
            except OSError:
                pass

            # Polling with animated rich spinner
            spinner_msg = (
                f"[bold #00d2ff]Waiting for browser authorization ({user_code})...[/bold #00d2ff]"
            )
            with console.status(spinner_msg, spinner="dots"):
                clean_token = wait_for_auth_token(
                    loopback_server=loopback_server,
                    device_code=device_code,
                    interval=interval,
                    timeout=expires_in,
                )

        except KeyboardInterrupt:
            if loopback_server:
                loopback_server.shutdown()
            console.print("\n[yellow]Device authorization cancelled.[/yellow]")
            fallback = typer.confirm("Would you like to enter a token manually?", default=True)
            if fallback:
                clean_token = typer.prompt(
                    "Enter your UbuntuBio Personal Access Token", hide_input=True
                ).strip()
            else:
                raise typer.Exit(code=1) from None
        except UbuntuBioError as exc:
            if loopback_server:
                loopback_server.shutdown()
            console.print(f"[bold red]Login failed:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc

    # Persist and verify session
    try:
        profile = auth_login(token=clean_token)
        orcid_id = profile.get("orcid_id", "Unknown")
        researcher_name = profile.get("name", "Researcher")
        username = profile.get("username")

        success_text = Text()
        success_text.append(f"  ✓ Welcome back, {researcher_name}!\n\n", style="bold #00ed64")
        if username:
            success_text.append("  Username:    ", style="bold #9ca3af")
            success_text.append(f"@{username}\n", style="bold #00ed64")
        success_text.append("  ORCID iD:    ", style="bold #9ca3af")
        success_text.append(f"{orcid_id} (https://orcid.org/{orcid_id})\n", style="bold #00d2ff")
        success_text.append("  Session:     ", style="bold #9ca3af")
        success_text.append("CLI Terminal Session\n", style="bold white")
        success_text.append("  Token Path:  ", style="bold #9ca3af")
        success_text.append("~/.config/ubuntubio/token\n", style="dim")
        success_text.append("  Status:      ", style="bold #9ca3af")
        success_text.append("● Sovereign Verified (54 AU States)\n", style="bold #00ed64")

        success_panel = Panel(
            success_text,
            title="[bold #00ed64]Authenticated Successfully[/bold #00ed64]",
            box=box.ROUNDED,
            border_style="#00ed64",
        )
        console.print(success_panel)

    except UbuntuBioError as exc:
        console.print(f"[bold red]Login failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def whoami() -> None:
    """Display information about the currently authenticated user.

    Fetches the verified researcher profile from the Hub, including:
      • Sovereign display name
      • Unique researcher handle ([bold #00ed64]@username[/bold #00ed64])
      • ORCID iD and verification status
      • African Union compliance status (non-human genomic data only)
    """
    try:
        profile = auth_whoami()
        table = Table(
            title="[bold #00ed64]UbuntuBio Authenticated Session[/bold #00ed64]",
            box=box.ROUNDED,
            header_style="bold #00d2ff",
            border_style="#1f2937",
        )
        table.add_column("Field", style="bold #9ca3af", width=16)
        table.add_column("Value")

        table.add_row("Researcher", f"[bold white]{profile.get('name', 'Unknown')}[/bold white]")
        if profile.get("username"):
            table.add_row("Username", f"[bold #00ed64]@{profile['username']}[/bold #00ed64]")
        orcid = profile.get("orcid_id", "Unknown")
        table.add_row("ORCID iD", f"[bold #00d2ff]{orcid}[/bold #00d2ff]")
        table.add_row("User ID", f"[dim]{profile.get('id', 'Unknown')}[/dim]")
        if profile.get("email"):
            table.add_row("Email", profile.get("email"))
        table.add_row(
            "Compliance",
            "[bold #00ed64]● Sovereign African Genomics (Non-human only)[/bold #00ed64]",
        )
        console.print(table)
    except UbuntuBioError as exc:
        console.print(f"[bold yellow]Not authenticated:[/bold yellow] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def logout() -> None:
    """Log out and remove stored credentials from ~/.config/ubuntubio/token."""
    if auth_logout():
        console.print("[green]Successfully logged out. Token deleted.[/green]")
    else:
        console.print("[dim]No active credentials found to remove.[/dim]")


@app.command()
def create(
    repo_id: Annotated[
        str,
        typer.Argument(
            help=(
                "Repository name or slug. If bare name (e.g. 'lassa-2024'), automatically "
                "defaults to personal namespace (@username/name). For orgs, use 'org/name'."
            )
        ),
    ],
    domain: Annotated[
        str,
        typer.Option(
            "--domain",
            "-d",
            help="Scientific domain: bacteria, virus, veterinary, plant, parasite, metagenome.",
        ),
    ],
    access: Annotated[
        str,
        typer.Option(
            "--access",
            "-a",
            help=(
                "Access tier: 'public' (open access), 'gated' (requires DTA approval), "
                "'private' (organization members only)."
            ),
        ),
    ] = "public",
    description: Annotated[
        str | None,
        typer.Option("--desc", help="Brief scientific abstract or description of the dataset."),
    ] = None,
    license: Annotated[
        str,
        typer.Option("--license", help="Data license (default: cc-by-4.0)."),
    ] = "cc-by-4.0",
    exist_ok: Annotated[
        bool,
        typer.Option("--exist-ok", help="Do not fail if repository already exists on Hub."),
    ] = False,
) -> None:
    """Create a new dataset repository on UbuntuBio Hub.

    [bold white]Repository ID Format:[/bold white]
      • [bold #00d2ff]Personal Dataset[/bold #00d2ff]: Pass a dataset name like [cyan]lassa[/cyan].
        The CLI prefixes your personal handle: [cyan]@username/lassa-2024[/cyan].
      • [bold #00d2ff]Organization Dataset[/bold #00d2ff]: Pass [cyan]org-slug/dataset-name[/cyan]
        (e.g., [cyan]ncdc/cholera-2024[/cyan]). Requires write membership in that organization.

    [bold white]Domains (--domain / -d):[/bold white]
      • [bold cyan]bacteria[/bold cyan]: Bacterial pathogens, AMR surveillance, clinical isolates
      • [bold cyan]virus[/bold cyan]: Viral genomics & surveillance (Ebola, Marburg, Lassa, Mpox)
      • [bold cyan]veterinary[/bold cyan]: Livestock genomics, zoonoses, animal trypanosomiasis
      • [bold cyan]plant[/bold cyan]: Indigenous African crops (cassava, yam, millet, sorghum)
      • [bold cyan]parasite[/bold cyan]: Malaria (Plasmodium falciparum), schistosomiasis
      • [bold cyan]metagenome[/bold cyan]: Metagenomic amplicon or shotgun sequencing from samples

    [bold white]Access Tiers (--access / -a):[/bold white]
      • [bold green]public[/bold green] (default): Freely discoverable and downloadable globally.
      • [bold yellow]gated[/bold yellow]: Discoverable; downloading requires DTA approval.
      • [bold red]private[/bold red]: Visible only to members of the parent organization.

    [bold white]Examples:[/bold white]
      [dim]# Create personal viral dataset (auto-namespaced to @username):[/dim]
      [green]$[/green] ubio create lassa-surveillance-2024 --domain virus

      [dim]# Create gated pathogen surveillance repository under an organization:[/dim]
      [green]$[/green] ubio create ncdc/cholera-2024 -d bacteria -a gated --desc "O1 isolates"

      [dim]# Create indigenous crop repository with custom license:[/dim]
      [green]$[/green] ubio create cassava-mosaic-res -d plant --license cc0-1.0
    """
    resolved_id = resolve_repo_slug(repo_id, command_name="create")
    try:
        repo = hub_create_repo(
            repo_id=resolved_id,
            domain=domain,
            access=access,
            description=description,
            license=license,
            exist_ok=exist_ok,
        )
        console.print(f"[bold green]✓ Created repository:[/bold green] {repo.get('slug')}")
        console.print(
            f"Access Tier: [cyan]{repo.get('access')}[/cyan] | "
            f"Domain: [cyan]{repo.get('domain')}[/cyan]"
        )
    except UbuntuBioError as exc:
        console.print(f"[bold red]Error creating repository:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def upload(
    repo_id: Annotated[
        str,
        typer.Argument(
            help="Target repository slug ('owner/name' or bare 'name' for personal dataset)."
        ),
    ],
    local_path: Annotated[Path, typer.Argument(help="Local file or directory path to upload.")],
    path_in_repo: Annotated[
        str | None,
        typer.Option(
            "--path-in-repo",
            "-p",
            help="Relative path inside repo. Defaults to the local file name.",
        ),
    ] = None,
    branch: Annotated[
        str, typer.Option("--branch", "-b", help="Target branch (default: main).")
    ] = "main",
    message: Annotated[
        str | None,
        typer.Option("--message", "-m", help="Git commit message describing this upload."),
    ] = None,
) -> None:
    """Upload a file or directory to an UbuntuBio repository.

    Files are version-controlled with Git and tracked via content-addressed storage.
    If uploading a directory, all child files are recursively scanned and committed.

    [bold white]Examples:[/bold white]
      [dim]# Upload a single FASTA file to your personal dataset:[/dim]
      [green]$[/green] ubio upload lassa-surveillance-2024 ./samples.fasta

      [dim]# Upload a file to a specific folder in an organization repository:[/dim]
      [green]$[/green] ubio upload ncdc/cholera-2024 ./data.vcf.gz -p variants/data.vcf.gz

      [dim]# Upload an entire analysis directory with a custom commit message:[/dim]
      [green]$[/green] ubio upload lassa-surveillance-2024 ./run_04/ -m "Add assembled contigs"
    """
    resolved_id = resolve_repo_slug(repo_id, command_name="upload")
    if not local_path.exists():
        console.print(f"[bold red]Error:[/bold red] Path '{local_path}' does not exist.")
        raise typer.Exit(code=1)

    try:
        if local_path.is_file():
            target_path = path_in_repo or local_path.name
            console.print(f"Uploading file '{local_path.name}' to '{resolved_id}/{target_path}'...")
            res = upload_file(
                repo_id=resolved_id,
                path_or_bytes=local_path,
                path_in_repo=target_path,
                branch=branch,
                message=message,
            )
            console.print(f"[bold green]✓ Upload successful:[/bold green] {res.get('status')}")
        elif local_path.is_dir():
            console.print(f"Uploading directory '{local_path}' to '{resolved_id}'...")
            res = upload_folder(
                repo_id=resolved_id,
                folder_path=local_path,
                branch=branch,
                message=message,
            )
            count = res.get("files_count", 0)
            console.print(
                f"[bold green]✓ Successfully uploaded and committed {count} file(s).[/bold green]"
            )
    except UbuntuBioError as exc:
        console.print(f"[bold red]Upload failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command(name="push")
def push(
    repo_id: Annotated[
        str,
        typer.Argument(
            help="Target repository slug ('owner/name' or bare 'name' for personal dataset)."
        ),
    ],
    local_path: Annotated[Path, typer.Argument(help="Local file or directory path to upload.")],
    path_in_repo: Annotated[
        str | None,
        typer.Option(
            "--path-in-repo",
            "-p",
            help="Relative path inside repo. Defaults to the local file name.",
        ),
    ] = None,
    branch: Annotated[
        str, typer.Option("--branch", "-b", help="Target branch (default: main).")
    ] = "main",
    message: Annotated[
        str | None,
        typer.Option("--message", "-m", help="Git commit message describing this upload."),
    ] = None,
) -> None:
    """Push (upload) a file or directory to an UbuntuBio repository. Alias for `ubio upload`."""
    upload(
        repo_id=repo_id,
        local_path=local_path,
        path_in_repo=path_in_repo,
        branch=branch,
        message=message,
    )


@app.command()
def download(
    repo_id: Annotated[
        str,
        typer.Argument(
            help="Target repository slug ('owner/name' or bare 'name' for personal dataset)."
        ),
    ],
    filename: Annotated[
        str | None,
        typer.Argument(
            help="File path in repo to download. If omitted, downloads full dataset snapshot."
        ),
    ] = None,
    revision: Annotated[
        str,
        typer.Option(
            "--revision", "-r", help="Git revision, commit SHA, or branch name (default: main)."
        ),
    ] = "main",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Custom destination file or directory path."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force redownload, bypassing local cache."),
    ] = False,
) -> None:
    """Download a specific file or full dataset snapshot from a repository.

    Supports sha256 checksum caching to avoid redundant downloads.

    [bold white]Examples:[/bold white]
      [dim]# Download entire dataset snapshot to current directory:[/dim]
      [green]$[/green] ubio download lassa-surveillance-2024

      [dim]# Download a specific FASTA file to custom location:[/dim]
      [green]$[/green] ubio download ncdc/cholera-2024 isolates.fasta -o ./local_isolates.fasta

      [dim]# Download snapshot from a specific branch or tag:[/dim]
      [green]$[/green] ubio download lassa-surveillance-2024 --revision v1.0.0 -o ./release_v1
    """
    resolved_id = resolve_repo_slug(repo_id, command_name="download")
    try:
        if filename:
            console.print(f"Downloading '{filename}' from '{resolved_id}'@{revision}...")
            target = download_file(
                repo_id=resolved_id,
                filename=filename,
                revision=revision,
                output_path=output,
                force_download=force,
            )
            console.print(f"[bold green]✓ Downloaded to:[/bold green] {target}")
        else:
            console.print(f"Downloading snapshot of '{resolved_id}'@{revision}...")
            target_dir = snapshot_download(
                repo_id=resolved_id,
                revision=revision,
                output_dir=output,
                force_download=force,
            )
            console.print(f"[bold green]✓ Snapshot downloaded to:[/bold green] {target_dir}")
    except UbuntuBioError as exc:
        console.print(f"[bold red]Download failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command(name="download-remote")
def download_remote(
    tsv_path: Annotated[
        Path,
        typer.Argument(
            help="Path to remote_files.tsv file containing external URLs and MD5 checksums."
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Target directory for downloaded files (default: ./remote_downloads).",
        ),
    ] = Path("./remote_downloads"),
) -> None:
    """Download external large genomic files listed in remote_files.tsv with MD5 verification.

    The remote_files.tsv format:
      [cyan]<filename>\\t<url>\\t<md5_checksum>[/cyan]

    [bold white]Examples:[/bold white]
      [dim]# Download remote mirrors with MD5 validation:[/dim]
      [green]$[/green] ubio download-remote ./remote_files.tsv --output-dir ./raw_data/
    """
    try:
        console.print(f"Downloading remote files from '{tsv_path}' to '{output_dir}'...")
        downloaded = download_remote_files(tsv_path=tsv_path, output_dir=output_dir)
        console.print(
            f"[bold green]✓ Downloaded and verified {len(downloaded)} file(s).[/bold green]"
        )

    except UbuntuBioError as exc:
        console.print(f"[bold red]Remote download failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(help="Keywords, pathogen names, or country tags to search."),
    ],
    domain: Annotated[
        str | None,
        typer.Option(
            "--domain",
            "-d",
            help="Filter by domain: bacteria, virus, veterinary, plant, parasite, metagenome.",
        ),
    ] = None,
) -> None:
    """Search for African bioinformatics datasets on the sovereign hub.

    Powered by full-text search across dataset slugs, titles, descriptions, and tags.

    [bold white]Examples:[/bold white]
      [dim]# Search by pathogen keyword:[/dim]
      [green]$[/green] ubio search "lassa"

      [dim]# Search within specific scientific domain:[/dim]
      [green]$[/green] ubio search "cholera" --domain bacteria
      [green]$[/green] ubio search "cassava" --domain plant
    """
    try:
        raw_results = hub_search(query=query, domain=domain)
        results: list[dict[str, Any]] = (
            raw_results.get("hits", []) if isinstance(raw_results, dict) else raw_results
        )
        if not results:
            console.print(f"[yellow]No datasets found matching '{query}'.[/yellow]")
            return

        table = Table(title=f"Search Results for '{query}'")
        table.add_column("Repository Slug", style="bold cyan")
        table.add_column("Domain", style="green")
        table.add_column("Access", style="yellow")
        table.add_column("Description")

        for r in results:
            table.add_row(
                r.get("slug", ""),
                r.get("domain", ""),
                r.get("access", ""),
                r.get("description") or "",
            )
        console.print(table)
    except UbuntuBioError as exc:
        console.print(f"[bold red]Search failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command(name="init")
def init(
    path: Annotated[
        Path,
        typer.Argument(
            help="Directory to initialize dataset in.",
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            "-y",
            help="Run in non-interactive mode using arguments or defaults without prompting.",
        ),
    ] = False,
    title: Annotated[
        str | None,
        typer.Option("--title", "-t", help="Dataset title."),
    ] = None,
    domain: Annotated[
        str | None,
        typer.Option(
            "--domain",
            "-d",
            help="Scientific domain: bacteria, virus, parasite, plant, veterinary, metagenome.",
        ),
    ] = None,
    country: Annotated[
        str | None,
        typer.Option(
            "--country",
            "-c",
            help="AU member state ISO-3166-1 alpha-2 country code (e.g. GH, NG, KE).",
        ),
    ] = None,
    taxon_id: Annotated[
        int | None,
        typer.Option("--taxon-id", help="NCBI Taxonomy ID (human 9606 is prohibited)."),
    ] = None,
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            help="Sequencing platform (e.g. ILLUMINA, OXFORD_NANOPORE, PACBIO).",
        ),
    ] = None,
    layout: Annotated[
        str | None,
        typer.Option("--layout", help="Library layout: paired or single."),
    ] = None,
    strategy: Annotated[
        str | None,
        typer.Option(
            "--strategy",
            help="Sequencing strategy: WGS, AMPLICON, RNA-Seq, TARGETED-CAPTURE, etc.",
        ),
    ] = None,
    access: Annotated[
        str | None,
        typer.Option("--access", help="Access tier: public, gated, or private."),
    ] = None,
) -> None:
    """Scaffold a new UbuntuBio dataset directory with templates and directory layout.

    Generates MIxS-compliant README.md with sequencing experiment frontmatter,
    samples.tsv template, remote_files.tsv, and reads/ directory.

    [bold white]Examples:[/bold white]
      [dim]# Interactive wizard:[/dim]
      [green]$[/green] ubio init ./lassa-surveillance

      [dim]# Non-interactive batch scaffold:[/dim]
      [green]$[/green] ubio init ./mpox-data -y -t "Mpox" -d virus -c NG --taxon-id 10244
    """
    if not non_interactive:
        console.print(
            Panel.fit(
                "[bold cyan]UbuntuBio Dataset Initialization Wizard[/bold cyan]\n"
                "Configure MIxS-compliant metadata and sequencing manifest.",
                border_style="cyan",
            )
        )
        if not title:
            title = typer.prompt("Dataset Title", default="African Pathogen Surveillance Study")
        if not domain:
            domain = typer.prompt(
                "Domain (bacteria, virus, parasite, plant, veterinary, metagenome)",
                default="virus",
            )
        if not country:
            country = typer.prompt(
                "AU Country Code (e.g. GH, NG, KE, ZA, EG)",
                default="GH",
            )
        if taxon_id is None:
            taxon_id_raw = typer.prompt("NCBI Taxonomy ID (9606 prohibited)", default="10566")
            try:
                taxon_id = int(taxon_id_raw)
            except ValueError as err:
                console.print("[bold red][ERROR] Taxonomy ID must be an integer.[/bold red]")
                raise typer.Exit(code=1) from err
        if not platform:
            platform = typer.prompt(
                "Sequencing Platform (ILLUMINA, OXFORD_NANOPORE, PACBIO, etc.)",
                default="ILLUMINA",
            )
        if not layout:
            layout = typer.prompt("Library Layout (paired, single)", default="paired")
        if not strategy:
            strategy = typer.prompt(
                "Library Strategy (WGS, AMPLICON, RNA-Seq, TARGETED-CAPTURE, etc.)",
                default="WGS",
            )
        if not access:
            access = typer.prompt("Access Tier (public, gated, private)", default="public")
    else:
        title = title or "African Pathogen Surveillance Study"
        domain = domain or "virus"
        country = country or "GH"
        taxon_id = taxon_id if taxon_id is not None else 10566
        platform = platform or "ILLUMINA"
        layout = layout or "paired"
        strategy = strategy or "WGS"
        access = access or "public"

    try:
        init_dataset(
            target_dir=path,
            title=title,
            domain=domain,
            country=country,
            taxon_id=taxon_id,
            access=access,
            platform=platform,
            library_strategy=strategy,
            library_layout=layout,
        )
        console.print(
            Panel.fit(
                f"[bold green][SUCCESS] Dataset scaffolded successfully at:[/bold green]\n"
                f"[cyan]{path.resolve()}[/cyan]\n\n"
                f"[bold white]Created Files:[/bold white]\n"
                f"  - [cyan]README.md[/cyan] (MIxS dataset card and sequencing manifest)\n"
                f"  - [cyan]samples.tsv[/cyan] (Sample metadata template)\n"
                f"  - [cyan]remote_files.tsv[/cyan] (External sequence file manifest)\n"
                f"  - [cyan]reads/[/cyan] (Local sequence data directory)\n\n"
                f"[bold white]Next Steps:[/bold white]\n"
                f"  1. Edit [cyan]{path}/README.md[/cyan] and fill in your library file names.\n"
                f"  2. Place FASTQ/BAM files in [cyan]{path}/reads/[/cyan] or record URLs "
                f"in [cyan]{path}/remote_files.tsv[/cyan].\n"
                f"  3. Run [bold #00d2ff]ubio check {path}[/bold #00d2ff] to verify compliance.",
                title="[bold green]UbuntuBio Dataset Initialized[/bold green]",
                border_style="green",
            )
        )
    except ClientValidationError as exc:
        console.print(f"[bold red][ERROR] Validation failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[bold red][ERROR] Failed to scaffold dataset:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command(name="check")
def check(
    path: Annotated[
        Path,
        typer.Argument(
            help="Directory containing the dataset to validate.",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Treat warnings as errors.",
        ),
    ] = False,
) -> None:
    """Validate local dataset metadata, MIxS compliance, and sequence file parity.

    Verifies:
      - README.md frontmatter syntax and mandatory MIxS fields
      - samples.tsv column headers and row validations (ISO date, AU country, Taxon ID)
      - Prohibited human taxon ID 9606 checks
      - Sequencing experiment block and library declaration
      - Two-way file parity (detects missing declared files and orphaned sequence files)
    """
    console.print(f"[bold cyan][INFO] Inspecting dataset at:[/bold cyan] {path.resolve()}")
    try:
        result = validate_local_dataset(path)
    except Exception as exc:
        console.print(f"[bold red][ERROR] Unexpected error during validation:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Dataset Validation Diagnostics", box=box.ROUNDED)
    table.add_column("Level", style="bold", width=10)
    table.add_column("Rule / Field", style="cyan", width=25)
    table.add_column("Message", style="white")

    has_errors = not result.valid or result.has_errors
    has_warnings = result.has_warnings

    for issue in result.issues:
        level_style = "bold red" if issue.level == "error" else "bold yellow"
        level_tag = f"[{level_style}][{issue.level.upper()}][/{level_style}]"
        field_name = issue.field or "-"
        table.add_row(level_tag, field_name, issue.message)

    if result.issues:
        console.print(table)
    else:
        console.print("[bold green][INFO] No issues or warnings found.[/bold green]")

    if result.sniff_results:
        seq_table = Table(title="Sequence File Screening Diagnostics", box=box.ROUNDED)
        seq_table.add_column("File", style="cyan")
        seq_table.add_column("Format", style="green")
        seq_table.add_column("Reads", justify="right")
        seq_table.add_column("Mean Len", justify="right")
        seq_table.add_column("GC%", justify="right")
        seq_table.add_column("Quality", style="magenta")
        seq_table.add_column("Status", style="bold")

        for sn in result.sniff_results:
            status_tag = (
                "[bold green]PASSED[/bold green]"
                if sn.is_valid and not sn.human_markers_detected
                else "[bold red]FAILED[/bold red]"
                if not sn.is_valid
                else "[bold yellow]SUSPICIOUS[/bold yellow]"
            )
            display_name = Path(sn.file_path).name
            seq_table.add_row(
                display_name,
                f"{sn.format} ({sn.compression})",
                str(sn.reads_sampled),
                f"{sn.mean_read_length:.1f} bp" if sn.reads_sampled > 0 else "-",
                f"{sn.gc_percent:.1f}%" if sn.reads_sampled > 0 else "-",
                sn.phred_encoding,
                status_tag,
            )
        console.print(seq_table)

    console.print(
        f"\n[dim]Summary: {len(result.errors)} errors, {len(result.warnings)} warnings, "
        f"{result.sample_count} samples validated, {result.library_count} libraries declared.[/dim]"
    )

    if has_errors or (strict and has_warnings):
        console.print(
            "[bold red][FAILED] Dataset validation failed. "
            "Please fix the errors listed above.[/bold red]"
        )
        raise typer.Exit(code=1)
    else:
        console.print("[bold green][PASSED] Dataset is valid and ready for upload.[/bold green]")


def main() -> None:
    """CLI application entrypoint."""
    app()


if __name__ == "__main__":
    main()
