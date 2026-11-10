"""Agent rule generator for IDE AI agents (Cursor, Antigravity, Claude Code)."""

from __future__ import annotations

from pathlib import Path

RULES_CONTENT = """# Groma Codebase Synchronization Rules

This project uses Groma to maintain deterministic codebase architecture and symbol maps.

## Operating Guidelines for AI Agents:

1. **Casual Chat & General Questions**:
   - Do NOT run Groma commands for general programming, syntax, or conceptual questions. Respond immediately with zero delay.

2. **Architecture & Symbol Discovery**:
   - When asked where symbols are defined, how dependencies connect, or how the project is structured, reference:
     - `.groma/architecture.md` (Core Hubs, frameworks, HTTP endpoints)
     - `.groma/file-map.md` (Classes, methods, signatures, exact line numbers)
     - `.groma/dependencies.md` (Per-file Imports & Imported-By tables)
   - If in doubt about whether the working tree is fresh, run `groma check`. If it reports STALE, run `groma update`.

3. **After Modifying Code**:
   - Whenever you create, edit, or delete source files, run `groma update` at the conclusion of your turn so the codebase skill and `.groma/` docs remain 100% synchronized with the working tree.
"""


def render_agent_rules(repo_root: Path) -> list[Path]:
    """Write agent rule files to .agents/rules/groma-sync.md and .cursorrules."""
    repo_root = repo_root.resolve()
    generated: list[Path] = []

    # 1. .agents/rules/groma-sync.md (Standard for multi-agent frameworks)
    agents_rules_dir = repo_root / ".agents" / "rules"
    agents_rules_dir.mkdir(parents=True, exist_ok=True)
    agents_rule_file = agents_rules_dir / "groma-sync.md"
    agents_rule_file.write_text(RULES_CONTENT, encoding="utf-8")
    generated.append(agents_rule_file)

    # 2. .cursorrules in repository root
    cursorrules_file = repo_root / ".cursorrules"
    # Overwrite if missing or already a Groma rule file
    should_write = True
    if cursorrules_file.is_file():
        try:
            existing = cursorrules_file.read_text(encoding="utf-8", errors="ignore")
            if "Groma" not in existing:
                should_write = False  # Respect user's existing custom cursorrules
        except OSError:
            should_write = True

    if should_write:
        cursorrules_file.write_text(RULES_CONTENT, encoding="utf-8")
        generated.append(cursorrules_file)

    return generated

