"""Multi-IDE MCP registration utility for Antigravity, Claude Desktop, and Cursor."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import NamedTuple


class RegistrationResult(NamedTuple):
    ide_name: str
    config_path: Path
    status: str  # "registered", "updated", "skipped", "error"
    message: str


def find_groma_executable() -> str:
    """Find the best executable path for running Groma in GUI/IDE contexts."""
    # 1. Check if 'groma' is in PATH and resolve absolute path
    which_groma = shutil.which("groma")
    if which_groma:
        return str(Path(which_groma).resolve())

    # 2. Check standard pipx locations (~/.local/bin/groma, ~/Library/Python/3.x/bin/groma)
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "groma",
        home / "Library" / "Python" / "3.15" / "bin" / "groma",
        home / "Library" / "Python" / "3.14" / "bin" / "groma",
        home / "Library" / "Python" / "3.13" / "bin" / "groma",
        home / "Library" / "Python" / "3.12" / "bin" / "groma",
        home / "Library" / "Python" / "3.11" / "bin" / "groma",
        home / "Library" / "Python" / "3.10" / "bin" / "groma",
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c.resolve())

    # 3. Fallback to current python executable
    return sys.executable


def _update_json_mcp_config(
    file_path: Path,
    server_name: str,
    server_config: dict[str, object],
    servers_key: str = "mcpServers",
) -> tuple[str, str]:
    """Safely insert or update an MCP server entry in a JSON configuration file."""
    data: dict[str, object] = {}
    if file_path.is_file():
        try:
            raw = file_path.read_text(encoding="utf-8").strip()
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    data = loaded
        except (OSError, json.JSONDecodeError) as e:
            return "error", f"Failed to parse existing JSON: {e}"

    if servers_key not in data or not isinstance(data[servers_key], dict):
        data[servers_key] = {}

    mcp_servers = data[servers_key]
    assert isinstance(mcp_servers, dict)

    is_new = server_name not in mcp_servers
    mcp_servers[server_name] = server_config

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return "registered" if is_new else "updated", "Successfully configured"
    except OSError as e:
        return "error", f"Could not write file: {e}"


def register_antigravity(executable: str) -> list[RegistrationResult]:
    """Register Groma MCP server in Google Antigravity global configurations."""
    results: list[RegistrationResult] = []
    home = Path.home()

    # Antigravity primary config files
    targets = [
        home / ".gemini" / "antigravity" / "mcp_servers.json",
        home / ".gemini" / "config" / "mcp_config.json",
    ]

    server_config = {
        "command": executable,
        "args": ["mcp", "."],
    }

    for target in targets:
        # Check if .gemini directory exists or can be created
        gemini_dir = home / ".gemini"
        if gemini_dir.is_dir() or target.parent.is_dir() or target.is_file():
            status, msg = _update_json_mcp_config(target, "groma", server_config)
            results.append(
                RegistrationResult(
                    ide_name="Google Antigravity",
                    config_path=target,
                    status=status,
                    message=msg,
                )
            )

    return results


def register_claude_desktop(executable: str) -> list[RegistrationResult]:
    """Register Groma MCP server in Claude Desktop configuration."""
    results: list[RegistrationResult] = []
    home = Path.home()

    if sys.platform == "darwin":
        target = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        target = (Path(appdata) if appdata else home / "AppData" / "Roaming") / "Claude" / "claude_desktop_config.json"
    else:
        target = home / ".config" / "Claude" / "claude_desktop_config.json"

    if target.parent.is_dir() or target.is_file():
        server_config = {
            "command": executable,
            "args": ["mcp", "."],
        }
        status, msg = _update_json_mcp_config(target, "groma", server_config)
        results.append(
            RegistrationResult(
                ide_name="Claude Desktop",
                config_path=target,
                status=status,
                message=msg,
            )
        )

    return results


def register_all_ides(executable: str | None = None) -> list[RegistrationResult]:
    """Detect and register Groma in all installed AI IDEs and editors."""
    exe = executable or find_groma_executable()
    all_results: list[RegistrationResult] = []

    all_results.extend(register_antigravity(exe))
    all_results.extend(register_claude_desktop(exe))

    return all_results

