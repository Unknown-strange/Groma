---
name: groma-knowledge
description: Deterministic codebase knowledge, symbol map, and dependency architecture for Groma.
version: 1.0.0
fingerprint: a3e5d699466efb6c6903d4f21f06e50a77833ca8dabbd928c81c16c81d25c7a1
generated_at: 2026-11-10T16:25:23.612994+00:00
frameworks:
  - Pydantic
  - Pytest
  - Typer
---

# Codebase Knowledge & Architecture Guide: Groma

This skill provides deterministic, up-to-date static analysis knowledge for the **Groma** repository.

---

## ⚠️ AI Agent Synchronization Rules

As an AI agent (Cursor, Claude Code, Antigravity, or Codex), follow these **strict operating rules**:

1. **Before Answering Architecture Questions / Starting Code Tasks**:
   - Run `groma check` in your terminal to verify this skill matches the current working tree.
   - If `groma check` reports **STALE**, run `groma update` before proceeding so your reference knowledge is 100% accurate.

2. **After Making Any File Edits / Refactors**:
   - Run `groma update` to deterministically re-parse changed files, recalculate the dependency graph, update `.groma/*.md`, and record the fresh fingerprint.

3. **Never Hand-Edit Knowledge Files**:
   - Never directly modify `.groma/*.md`, `.groma/*.json`, or this `SKILL.md` file. All updates must be produced deterministically by `groma update`.

---

## 📚 Deep Knowledge References

For detailed code analysis and symbols, inspect the generated documents in `.groma/`:

- **[System Architecture & Hubs](file://.groma/architecture.md)** (`.groma/architecture.md`)
  - Project summary, detected frameworks, top Core Hubs (in-degree ranking), and HTTP API route tables.
- **[File & Symbol Map](file://.groma/file-map.md)** (`.groma/file-map.md`)
  - Complete index of all source files with classes, bases, methods, functions, type signatures, and line numbers.
- **[Dependency & Impact Graph](file://.groma/dependencies.md)** (`.groma/dependencies.md`)
  - Per-file breakdown of what each file imports and all files that import it.

---

## ⚡ Quick CLI Reference

```bash
# Verify freshness and check impact radius of unstaged/staged changes
groma check

# Re-parse changed files and synchronize all docs
groma update

# Rebuild full baseline scan
groma scan
```
