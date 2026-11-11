# Groma Codebase Discovery & Synchronization Rules

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
