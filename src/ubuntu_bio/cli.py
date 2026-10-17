"""Command-line interface (CLI) for UbuntuBio (M2-07)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ubuntu_bio import __version__
from ubuntu_bio.auth import login as auth_login
from ubuntu_bio.auth import logout as auth_logout
from ubuntu_bio.auth import whoami as auth_whoami
from ubuntu_bio.download import download_file, download_remote_files, snapshot_download
from ubuntu_bio.exceptions import UbuntuBioError
from ubuntu_bio.hub import create_repo as hub_create_repo
from ubuntu_bio.search import search as hub_search
from ubuntu_bio.upload import upload_file, upload_folder

app = typer.Typer(
    name="ubio",
    help="UbuntuBio CLI - African Bioinformatics Data Hub client.",
    no_args_is_help=True,
)
console = Console()


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
            help="Personal Access Token (ubp_...). If omitted, you will be prompted securely.",
        ),
    ] = None,
) -> None:
    """Log in to UbuntuBio Hub using your Personal Access Token."""
    if not token:
        token = typer.prompt("Enter your UbuntuBio Personal Access Token", hide_input=True)

    try:
        profile = auth_login(token=token.strip())
        console.print("[bold green]✓ Successfully authenticated![/bold green]")
        console.print(f"Researcher: [bold]{profile.get('name')}[/bold]")
        console.print(f"ORCID ID:   [cyan]{profile.get('orcid_id')}[/cyan]")
    except UbuntuBioError as exc:
        console.print(f"[bold red]Login failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def whoami() -> None:
    """Display information about the currently authenticated user."""
    try:
        profile = auth_whoami()
        table = Table(title="UbuntuBio Authenticated Session", show_header=False)
        table.add_row("Name", profile.get("name", "Unknown"))
        table.add_row("ORCID iD", profile.get("orcid_id", "Unknown"))
        table.add_row("User ID", profile.get("id", "Unknown"))
        if profile.get("email"):
            table.add_row("Email", profile.get("email"))
        console.print(table)
    except UbuntuBioError as exc:
        console.print(f"[bold yellow]Not authenticated:[/bold yellow] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def logout() -> None:
    """Log out and remove stored authentication credentials."""
    if auth_logout():
        console.print("[green]Successfully logged out. Token deleted.[/green]")
    else:
        console.print("[dim]No active credentials found to remove.[/dim]")


@app.command()
def create(
    repo_id: Annotated[str, typer.Argument(help="Repository slug in 'owner/name' format.")],
    domain: Annotated[
        str,
        typer.Option(
            "--domain",
            "-d",
            help="Domain (bacteria, virus, veterinary, plant, parasite, metagenome).",
        ),
    ],
    access: Annotated[
        str,
        typer.Option("--access", "-a", help="Access tier: public, gated, private."),
    ] = "public",
    description: Annotated[
        str | None,
        typer.Option("--desc", help="Brief scientific description of the dataset."),
    ] = None,
    license: Annotated[
        str,
        typer.Option("--license", help="Data license (default: cc-by-4.0)."),
    ] = "cc-by-4.0",
) -> None:
    """Create a new dataset repository on UbuntuBio Hub."""
    try:
        repo = hub_create_repo(
            repo_id=repo_id,
            domain=domain,
            access=access,
            description=description,
            license=license,
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
    repo_id: Annotated[str, typer.Argument(help="Target repository slug ('owner/name').")],
    local_path: Annotated[Path, typer.Argument(help="Local file or directory to upload.")],
    path_in_repo: Annotated[
        str | None,
        typer.Option("--path-in-repo", help="Relative destination path inside the repository."),
    ] = None,
    branch: Annotated[str, typer.Option("--branch", "-b", help="Target branch.")] = "main",
    message: Annotated[str | None, typer.Option("--message", "-m", help="Commit message.")] = None,
) -> None:
    """Upload a file or directory to an UbuntuBio repository."""
    if not local_path.exists():
        console.print(f"[bold red]Error:[/bold red] Path '{local_path}' does not exist.")
        raise typer.Exit(code=1)

    try:
        if local_path.is_file():
            target_path = path_in_repo or local_path.name
            console.print(f"Uploading file '{local_path.name}' to '{repo_id}/{target_path}'...")
            res = upload_file(
                repo_id=repo_id,
                path_or_bytes=local_path,
                path_in_repo=target_path,
                branch=branch,
                message=message,
            )
            console.print(f"[bold green]✓ Upload successful:[/bold green] {res.get('status')}")
        elif local_path.is_dir():
            console.print(f"Uploading directory '{local_path}' to '{repo_id}'...")
            res = upload_folder(
                repo_id=repo_id,
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


@app.command()
def download(
    repo_id: Annotated[str, typer.Argument(help="Target repository slug ('owner/name').")],
    filename: Annotated[
        str | None,
        typer.Argument(help="Specific file to download. If omitted, downloads full snapshot."),
    ] = None,
    revision: Annotated[
        str, typer.Option("--revision", "-r", help="Git revision or branch.")
    ] = "main",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Custom destination file or directory path."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force redownload, bypassing cache."),
    ] = False,
) -> None:
    """Download a file or full snapshot from a repository."""
    try:
        if filename:
            console.print(f"Downloading '{filename}' from '{repo_id}'@{revision}...")
            target = download_file(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                output_path=output,
                force_download=force,
            )
            console.print(f"[bold green]✓ Downloaded to:[/bold green] {target}")
        else:
            console.print(f"Downloading snapshot of '{repo_id}'@{revision}...")
            target_dir = snapshot_download(
                repo_id=repo_id,
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
    tsv_path: Annotated[Path, typer.Argument(help="Path to remote_files.tsv file.")],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Target directory for downloaded files."),
    ] = Path("./remote_downloads"),
) -> None:
    """Download all external files listed in a remote_files.tsv with MD5 verification."""
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
    query: Annotated[str, typer.Argument(help="Keywords to search.")],
    domain: Annotated[
        str | None,
        typer.Option("--domain", "-d", help="Filter by biological domain."),
    ] = None,
) -> None:
    """Search for African bioinformatics datasets on the hub."""
    try:
        results = hub_search(query=query, domain=domain)
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


def main() -> None:
    """CLI application entrypoint."""
    app()


if __name__ == "__main__":
    main()
