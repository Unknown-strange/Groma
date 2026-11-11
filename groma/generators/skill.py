"""Skill generator for .agents/skills/<project>/SKILL.md."""

from __future__ import annotations

from pathlib import Path

from groma.schema import Manifest

SKILLS_DIR_NAME = Path(".agents") / "skills"


def generate_skill_doc(manifest: Manifest, project_name: str | None = None) -> str:
    """Generate the complete content for SKILL.md including YAML frontmatter and AI rules."""
    p_name = project_name or manifest.project_name
    skill_name = f"{p_name.lower().replace(' ', '-').replace('_', '-')}-knowledge"

    if manifest.languages:
        languages_yaml = "\nlanguages:\n" + "\n".join(f"  - {lang}" for lang in manifest.languages)
    else:
        languages_yaml = "\nlanguages: []"

    content = f"""---
name: {skill_name}
description: Deterministic codebase knowledge, symbol map, and dependency architecture for {p_name}.
version: 1.0.0
fingerprint: {manifest.fingerprint}
generated_at: {manifest.generated_at}{languages_yaml}
---

# Codebase Knowledge & Architecture Guide: {p_name}

This skill provides deterministic, up-to-date static analysis knowledge for the **{p_name}** repository across all indexed languages.

---

## ⚠️ AI Agent Discovery & Synchronization Rules

As an AI agent (Antigravity, Cursor, Claude Code, or Codex), follow these **strict operating rules**:

1. **Always Query Groma First (Never Use Blind `find` or `grep` First)**:
   - When searching for classes, functions, database seeders, migrations, models, or HTTP routes, use the `groma_find_symbol` MCP tool or run `groma find <query>` in the terminal.
   - Consult `.groma/architecture.md`, `.groma/file-map.md`, and `.groma/dependencies.md` before scanning the filesystem manually.

2. **Before Answering Architecture Questions / Starting Code Tasks**:
   - Run `groma check` (or call `groma_sync_status`) to verify this skill matches the current working tree.
   - If `groma check` reports **STALE**, run `groma update` before proceeding so your reference knowledge is 100% accurate.

3. **After Making Any File Edits / Refactors**:
   - Run `groma update` to deterministically re-parse changed files, recalculate the dependency graph, update `.groma/*.md`, and record the fresh fingerprint.

4. **Never Hand-Edit Knowledge Files**:
   - Never directly modify `.groma/*.md`, `.groma/*.json`, or this `SKILL.md` file. All updates must be produced deterministically by `groma update`.

---

## 📚 Deep Knowledge References

For detailed code analysis and symbols, inspect the generated documents in `.groma/`:

- **[System Architecture & Hubs](file://.groma/architecture.md)** (`.groma/architecture.md`)
  - Project summary, indexed languages, top Core Hubs (in-degree ranking), and HTTP API route tables.
- **[File & Symbol Map](file://.groma/file-map.md)** (`.groma/file-map.md`)
  - Complete index of all source files with classes, bases, methods, functions, type signatures, and line numbers.
- **[Dependency & Impact Graph](file://.groma/dependencies.md)** (`.groma/dependencies.md`)
  - Per-file breakdown of what each file imports and all files that import it.

---

## ⚡ Quick CLI & MCP Reference

```bash
# Instant symbol, class, seeder, migration, or route lookup
groma find <query>

# Verify freshness and check impact radius of unstaged/staged changes
groma check

# Re-parse changed files and synchronize all docs
groma update

# Start the Model Context Protocol (MCP) server over stdio
groma mcp
```
"""
    return content


def render_skill_doc(
    repo_root: Path, manifest: Manifest, project_name: str | None = None
) -> Path:
    """Write SKILL.md to .agents/skills/<project_name>/SKILL.md and return its path."""
    p_name = project_name or manifest.project_name
    skill_dir_name = f"{p_name.lower().replace(' ', '-').replace('_', '-')}-knowledge"
    target_dir = repo_root.resolve() / SKILLS_DIR_NAME / skill_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    skill_path = target_dir / "SKILL.md"
    skill_content = generate_skill_doc(manifest, project_name=p_name)
    skill_path.write_text(skill_content, encoding="utf-8")
    return skill_path
