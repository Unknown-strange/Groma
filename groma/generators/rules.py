"""Agent rule and MCP configuration generator for IDE AI agents (Cursor, Antigravity, Claude Code)."""

from __future__ import annotations

import json
from pathlib import Path

RULES_CONTENT = """# Groma Codebase Discovery & Synchronization Rules

This project uses **Groma** to maintain deterministic multi-language codebase architecture, symbol maps, and an active MCP query index.

## Operating Guidelines for AI Agents:

1. **Casual Chat & General Questions**:
   - Do NOT run Groma commands for general programming, syntax, or conceptual questions. Respond immediately with zero delay.

2. **Codebase & Symbol Discovery (Check Groma BEFORE `find` / `grep`)**:
   - Never fall back to brute-force shell `find` or `grep` before checking Groma.
   - To locate any class, function, method, database seeder, migration, or HTTP route:
     - Call the **`groma_find_symbol`** MCP tool (if connected), OR
     - Run **`groma find <query>`** in the terminal, OR
     - Consult `.groma/architecture.md`, `.groma/file-map.md`, and `.groma/dependencies.md`.
   - Before refactoring a file, check its blast radius via `groma_impact_radius` or `.groma/dependencies.md`.

3. **After Modifying Code**:
   - Whenever you create, edit, or delete source files, run `groma update` (or `groma_sync_status(auto_update=True)`) at the conclusion of your turn so the codebase skill and `.groma/` docs remain 100% synchronized with the working tree.
"""


def render_agent_rules(repo_root: Path) -> list[Path]:
    """Write agent rule files (.agents/rules/groma-sync.md, .cursorrules) and .cursor/mcp.json."""
    repo_root = repo_root.resolve()
    generated: list[Path] = []

    # 1. .agents/rules/groma-sync.md (Standard for Antigravity & multi-agent frameworks)
    agents_rules_dir = repo_root / ".agents" / "rules"
    agents_rules_dir.mkdir(parents=True, exist_ok=True)
    agents_rule_file = agents_rules_dir / "groma-sync.md"
    agents_rule_file.write_text(RULES_CONTENT, encoding="utf-8")
    generated.append(agents_rule_file)

    # 2. .cursorrules in repository root
    cursorrules_file = repo_root / ".cursorrules"
    should_write = True
    if cursorrules_file.is_file():
        try:
            existing = cursorrules_file.read_text(encoding="utf-8", errors="ignore")
            if "Groma" not in existing:
                should_write = False  # Respect user's custom non-Groma cursorrules
        except OSError:
            should_write = True

    if should_write:
        cursorrules_file.write_text(RULES_CONTENT, encoding="utf-8")
        generated.append(cursorrules_file)

    # 3. .cursor/mcp.json (Registers Groma MCP server automatically in Cursor/IDEs)
    cursor_dir = repo_root / ".cursor"
    mcp_config_path = cursor_dir / "mcp.json"
    mcp_data: dict[str, dict[str, object]] = {"mcpServers": {}}
    if mcp_config_path.is_file():
        try:
            loaded = json.loads(mcp_config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                mcp_data = loaded
                if not isinstance(mcp_data.get("mcpServers"), dict):
                    mcp_data["mcpServers"] = {}
        except (OSError, json.JSONDecodeError):
            mcp_data = {"mcpServers": {}}

    mcp_data["mcpServers"]["groma"] = {
        "command": "groma",
        "args": ["mcp", "."],
    }
    cursor_dir.mkdir(parents=True, exist_ok=True)
    mcp_config_path.write_text(json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8")
    generated.append(mcp_config_path)

    return generated
