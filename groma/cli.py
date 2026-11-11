"""Typer + Rich CLI Orchestrator for Groma: scan, check, update, find, and mcp."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from groma import __version__
from groma.generators import generate_all_docs
from groma.graph import DependencyGraph
from groma.manifest import (
    build_manifest,
    diff_manifests,
    load_manifest,
    save_manifest,
)
from groma.mcp_server import ensure_state_loaded, run_mcp_stdio_server, search_knowledge_base
from groma.parsers import build_file_index, load_file_index, save_file_index
from groma.scanner import scan_repository

app = typer.Typer(
    name="groma",
    help="Deterministic codebase knowledge, symbol search & MCP server for IDE AI agents.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]Groma[/bold cyan] version [bold green]{__version__}[/bold green]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show Groma version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Groma CLI root callback."""


@app.command(name="scan")
def scan_cmd(
    target_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to repository root.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Perform a full baseline scan, parse symbols, build graph, and generate docs."""
    with console.status("[bold cyan]Scanning repository and building knowledge graph...[/bold cyan]"):
        # 1. Scan files and languages across the repo
        scan_result = scan_repository(target_dir)

        # 2. Build SHA-256 manifest
        manifest = build_manifest(target_dir, scan_result.files, scan_result.languages)

        # 3. Parse ASTs & universal multi-language symbols
        file_index = build_file_index(target_dir, scan_result.files)

        # 4. Build Dependency Graph
        graph = DependencyGraph(file_index)

        # 5. Generate Markdown, Skill docs, and MCP/Agent rules
        generated_docs = generate_all_docs(target_dir, manifest, file_index, graph)

        # 6. Persist machine state
        save_manifest(target_dir, manifest)
        save_file_index(target_dir, file_index)

    # Output Summary Table
    table = Table(title="[bold green]Groma Baseline Scan Summary[/bold green]", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Project Name", manifest.project_name)
    table.add_row("Tracked Files", str(len(manifest.files)))
    table.add_row(
        "Indexed Languages",
        ", ".join(manifest.languages) if manifest.languages else "None detected",
    )
    table.add_row("Core Hubs", str(len(graph.core_hubs())))
    table.add_row("Summary Fingerprint", f"[bold yellow]{manifest.fingerprint[:16]}...[/bold yellow]")
    table.add_row("Generated Docs", f"{len(generated_docs)} files (.groma/, .agents/, .cursor/)")

    console.print(table)
    console.print(
        Panel(
            "[bold green]✓ Baseline scan complete![/bold green]\n"
            "• Query symbols anytime with [bold cyan]groma find <query>[/bold cyan]\n"
            "• Verify freshness with [bold cyan]groma check[/bold cyan] or sync changes with "
            "[bold cyan]groma update[/bold cyan]",
            border_style="green",
        )
    )


@app.command(name="check")
def check_cmd(
    target_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to repository root.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Read-only check of disk state vs manifest.json. Reports staleness and impact radius."""
    old_manifest = load_manifest(target_dir)
    if old_manifest is None:
        console.print(
            Panel(
                "[bold red]No Groma baseline found![/bold red]\n"
                f"Missing .groma/manifest.json in `{target_dir}`.\n"
                "Please run [bold cyan]groma scan[/bold cyan] first to establish a baseline.",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    with console.status("[bold cyan]Checking working tree against baseline...[/bold cyan]"):
        scan_result = scan_repository(target_dir)
        current_manifest = build_manifest(
            target_dir,
            scan_result.files,
            scan_result.languages,
            previous_manifest=old_manifest,
            project_name=old_manifest.project_name,
        )
        diff = diff_manifests(old_manifest, current_manifest)

    if diff.is_clean:
        console.print(
            Panel(
                f"[bold green]✓ UP TO DATE[/bold green]\n"
                f"Project: [cyan]{old_manifest.project_name}[/cyan]\n"
                f"Fingerprint: [yellow]{old_manifest.fingerprint}[/yellow]\n"
                f"Files: [white]{len(old_manifest.files)} source files verified[/white]",
                border_style="green",
            )
        )
        raise typer.Exit(code=0)

    # Working tree is stale: load index to compute reverse impact radius
    old_index = load_file_index(target_dir)
    impact_files: list[str] = []
    if old_index is not None:
        graph = DependencyGraph(old_index)
        impact_files = graph.impact_radius(diff.changed_files)

    stale_lines: list[str] = [
        "[bold red]⚠️ STALE: Working tree has changed since last Groma sync![/bold red]",
        f"Baseline Fingerprint: [dim]{old_manifest.fingerprint[:16]}...[/dim]",
        f"Current Fingerprint:  [bold yellow]{current_manifest.fingerprint[:16]}...[/bold yellow]",
        "",
    ]

    if diff.modified:
        stale_lines.append(f"[bold yellow]Modified ({len(diff.modified)}):[/bold yellow]")
        for m in diff.modified:
            stale_lines.append(f"  • {m}")

    if diff.added:
        stale_lines.append(f"[bold green]Added ({len(diff.added)}):[/bold green]")
        for a in diff.added:
            stale_lines.append(f"  • {a}")

    if diff.deleted:
        stale_lines.append(f"[bold red]Deleted ({len(diff.deleted)}):[/bold red]")
        for d in diff.deleted:
            stale_lines.append(f"  • {d}")

    if diff.renamed:
        stale_lines.append(f"[bold cyan]Renamed ({len(diff.renamed)}):[/bold cyan]")
        for old_p, new_p in diff.renamed.items():
            stale_lines.append(f"  • {old_p} -> {new_p}")

    if impact_files:
        stale_lines.append("")
        stale_lines.append(
            f"[bold magenta]Impact Radius ({len(impact_files)} dependent files affected):[/bold magenta]"
        )
        for imp in impact_files:
            stale_lines.append(f"  ↳ {imp}")

    stale_lines.extend([
        "",
        "Please run [bold cyan]groma update[/bold cyan] to re-synchronize.",
    ])

    console.print(Panel("\n".join(stale_lines), border_style="yellow"))
    raise typer.Exit(code=1)


@app.command(name="update")
def update_cmd(
    target_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to repository root.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Fast incremental rebuild. Re-parses ONLY changed files and synchronizes docs."""
    old_manifest = load_manifest(target_dir)
    old_index = load_file_index(target_dir)

    if old_manifest is None or old_index is None:
        console.print("[yellow]No existing baseline found. Running full scan...[/yellow]")
        scan_cmd(target_dir)
        return

    with console.status("[bold cyan]Detecting changes for incremental update...[/bold cyan]"):
        scan_result = scan_repository(target_dir)
        current_manifest = build_manifest(
            target_dir,
            scan_result.files,
            scan_result.languages,
            previous_manifest=old_manifest,
            project_name=old_manifest.project_name,
        )
        diff = diff_manifests(old_manifest, current_manifest)

        if diff.is_clean:
            console.print("[green]Codebase is already up to date. Nothing to synchronize.[/green]")
            raise typer.Exit(code=0)

        # Incremental parse: re-parse only changed files
        changed_set = set(diff.changed_files)
        new_index = build_file_index(
            target_dir,
            scan_result.files,
            previous_index=old_index,
            changed_files=changed_set,
            project_name=old_manifest.project_name,
        )

        # Prune deleted files
        for d in diff.deleted:
            new_index.files.pop(d, None)

        # Recompute graph and docs
        graph = DependencyGraph(new_index)
        generate_all_docs(target_dir, current_manifest, new_index, graph)

        # Save fresh state
        save_manifest(target_dir, current_manifest)
        save_file_index(target_dir, new_index)

    console.print(
        Panel(
            f"[bold green]✓ SYNCHRONIZED[/bold green]\n"
            f"Project: [cyan]{current_manifest.project_name}[/cyan]\n"
            f"Re-parsed: [yellow]{len(diff.changed_files)} changed files[/yellow]\n"
            f"Deleted: [red]{len(diff.deleted)} files[/red]\n"
            f"New Fingerprint: [bold green]{current_manifest.fingerprint}[/bold green]",
            border_style="green",
        )
    )


@app.command(name="find")
def find_cmd(
    query: Annotated[
        str,
        typer.Argument(help="Symbol, class, function, route, or filename substring to search."),
    ],
    target_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to repository root.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Fast sub-10ms search across all indexed files, classes, methods, functions, and routes."""
    _, file_index, _ = ensure_state_loaded(target_dir)
    matches = search_knowledge_base(file_index, query)

    if not matches:
        console.print(f"[yellow]No files, symbols, or routes found matching '{query}'.[/yellow]")
        raise typer.Exit(code=1)

    table = Table(
        title=f"[bold green]Groma Search Results for '{query}' ({len(matches)} matches)[/bold green]",
        show_header=True,
    )
    table.add_column("Type", style="cyan", no_wrap=True)
    table.add_column("Symbol / Name", style="bold white")
    table.add_column("Location", style="yellow")
    table.add_column("Details", style="dim")

    for m in matches[:50]:
        table.add_row(
            str(m["kind"]).upper(),
            str(m["name"]),
            f"{m['file']}:{m['line']}",
            str(m["detail"]),
        )

    console.print(table)


@app.command(name="mcp")
def mcp_cmd(
    target_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to repository root.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    register: Annotated[
        bool,
        typer.Option(
            "--register",
            "-r",
            help="Register Groma MCP server into Antigravity and Claude configs.",
        ),
    ] = False,
) -> None:
    """Start the Groma Model Context Protocol (MCP) server over stdio, or register it."""
    if register:
        _perform_mcp_registration()
        return

    run_mcp_stdio_server(target_dir)


@app.command(name="register")
def register_cmd() -> None:
    """Automatically register Groma MCP server into Google Antigravity and Claude Desktop."""
    _perform_mcp_registration()


def _perform_mcp_registration() -> None:
    """Detect installed AI IDEs and configure Groma MCP with absolute binary path."""
    from groma.mcp_registry import find_groma_executable, register_all_ides

    exe_path = find_groma_executable()
    console.print(f"[bold cyan]Resolved Groma executable:[/bold cyan] [yellow]{exe_path}[/yellow]\n")

    results = register_all_ides(exe_path)

    if not results:
        console.print("[yellow]No supported global IDE configuration folders detected.[/yellow]")
        console.print("You can manually configure Groma in your editor with:")
        console.print(f"  Command: {exe_path}\n  Args: ['mcp', '.']\n")
        return

    table = Table(title="[bold green]Groma MCP IDE Auto-Registration[/bold green]", show_header=True)
    table.add_column("Environment / IDE", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Config File", style="yellow")
    table.add_column("Message", style="dim")

    for r in results:
        status_color = "green" if r.status in ("registered", "updated") else "red"
        table.add_row(
            r.ide_name,
            f"[{status_color}]{r.status.upper()}[/{status_color}]",
            str(r.config_path),
            r.message,
        )

    console.print(table)
    console.print(
        Panel(
            "[bold green]✓ Registration complete![/bold green]\n"
            "• Restart or reload your AI editor (Antigravity / Claude) to activate Groma tools.\n"
            "• Groma tools (`groma_overview`, `groma_find_symbol`) will now appear natively.",
            border_style="green",
        )
    )
