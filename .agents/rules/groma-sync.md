---
trigger: always_on
---

# Groma Codebase Discovery & Synchronization Rules

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
