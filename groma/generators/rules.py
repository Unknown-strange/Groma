"""Agent rule and MCP configuration generator for IDE AI agents (Antigravity, Claude Code, Cursor, etc.)."""

from __future__ import annotations

import json
import re
from pathlib import Path

RULES_CONTENT = """# Groma Codebase Discovery & Synchronization Rules

This project uses **Groma** to maintain deterministic multi-language codebase architecture, symbol maps, and an active MCP query index.

## Operating Guidelines for AI Agents

1. **Casual Chat & General Questions**:
   - Do NOT run Groma commands for general programming, syntax, or conceptual questions. Respond immediately with zero delay.

2. **Codebase & Symbol Discovery (Use Groma First, Fall Back to `grep` / `find`)**:
   - **Always try Groma first**: To discover symbols, routes, database tables/seeders, dependencies, or architectural hubs:
     - Call the **`groma_find_symbol`**, **`groma_file_details`**, or **`groma_impact_radius`** MCP tools (if `groma_*` tools are lazy-loaded/deferred, inspect their tool schemas first before calling `call_mcp_tool`), OR
     - Run **`groma find <query>`** in the terminal, OR
     - Consult `.groma/architecture.md`, `.groma/file-map.md`, and `.groma/dependencies.md`.
   - **Targeted Code Inspection**: Once Groma pinpoints the relevant file and line range, use `read_file` on that targeted range to inspect exact runtime/conditional logic.
   - **When to fall back to `grep` / `find`**: Groma is optimized for code symbols, routes, and structure. If Groma does not locate what you need (e.g. searching for raw text, specific error messages, arbitrary strings, or non-code config values), you should then fall back to `grep`, `rg`, or `find`.
   - Before refactoring a file, check its blast radius via `groma_impact_radius` or `.groma/dependencies.md`.

3. **After Modifying Code**:
   - Whenever you create, edit, or delete source files, run `groma update` (or `groma_sync_status(auto_update=True)`) at the conclusion of your turn so the codebase skill and `.groma/` docs remain 100% synchronized with the working tree.
"""

ALWAYS_ON_FRONTMATTER = "---\ntrigger: always_on\n---\n\n"
GROMA_START_MARKER = "<!-- groma:start -->"
GROMA_END_MARKER = "<!-- groma:end -->"


def _write_mcp_json(mcp_path: Path) -> Path:
    """Safely insert or update the Groma MCP server entry in a JSON config file."""
    mcp_data: dict[str, dict[str, object]] = {"mcpServers": {}}
    if mcp_path.is_file():
        try:
            raw = mcp_path.read_text(encoding="utf-8").strip()
            if raw:
                loaded = json.loads(raw)
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
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8")
    return mcp_path


def _upsert_agents_md(repo_root: Path) -> Path:
    """Create or update the Groma section in root AGENTS.md without clobbering user rules."""
    agents_md = repo_root / "AGENTS.md"
    block = f"{GROMA_START_MARKER}\n{RULES_CONTENT.rstrip()}\n{GROMA_END_MARKER}\n"

    if agents_md.is_file():
        existing = agents_md.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            rf"{re.escape(GROMA_START_MARKER)}.*?{re.escape(GROMA_END_MARKER)}\n?",
            re.DOTALL,
        )
        if pattern.search(existing):
            updated = pattern.sub(block, existing, count=1)
        else:
            sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
            updated = f"{existing.rstrip()}{sep}{block}" if existing.strip() else block
        agents_md.write_text(updated, encoding="utf-8")
    else:
        agents_md.write_text(block, encoding="utf-8")

    return agents_md


def render_agent_rules(repo_root: Path) -> list[Path]:
    """Write always-on agent rule files (AGENTS.md, .agents/rules/groma-sync.md, .cursorrules) and MCP configs."""
    repo_root = repo_root.resolve()
    generated: list[Path] = []

    # 1. AGENTS.md in repository root (Always-on standard for Antigravity, Claude Code, Codex, Cursor, Windsurf)
    generated.append(_upsert_agents_md(repo_root))

    # 2. .agents/rules/groma-sync.md with trigger: always_on for Antigravity unconditional loading
    agents_rules_dir = repo_root / ".agents" / "rules"
    agents_rules_dir.mkdir(parents=True, exist_ok=True)
    agents_rule_file = agents_rules_dir / "groma-sync.md"
    agents_rule_file.write_text(f"{ALWAYS_ON_FRONTMATTER}{RULES_CONTENT}", encoding="utf-8")
    generated.append(agents_rule_file)

    # 3. .cursorrules in repository root
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

    # 4. .mcp.json in repository root (Vendor-neutral open MCP standard)
    generated.append(_write_mcp_json(repo_root / ".mcp.json"))

    # 5. .cursor/mcp.json (Cursor IDE workspace integration)
    generated.append(_write_mcp_json(repo_root / ".cursor" / "mcp.json"))

    return generated
