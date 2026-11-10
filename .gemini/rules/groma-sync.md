# Groma Codebase Synchronization Rules

This project uses **Groma** to maintain deterministic codebase architecture and symbol maps.

## Operating Guidelines for AI Agents:

1. **Casual Chat & General Questions**:
   - Do NOT run Groma commands for general programming, syntax, or conceptual questions. Respond immediately.

2. **Architecture & Symbol Discovery**:
   - When asked where symbols are defined, how dependencies connect, or how the project is structured, consult:
     - `.groma/architecture.md` (Core Hubs, frameworks, HTTP endpoints)
     - `.groma/file-map.md` (Classes, methods, signatures, exact line numbers)
     - `.groma/dependencies.md` (Per-file Imports & Imported-By tables)
   - If in doubt about whether the working tree is fresh, run `groma check`. If it reports `STALE`, run `groma update`.

3. **After Modifying Code**:
   - Whenever you create, edit, or delete source files, run `groma update` at the conclusion of your turn so the codebase skill and `.groma/` docs remain 100% synchronized with the working tree.

