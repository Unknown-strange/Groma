"""Built-in Model Context Protocol (MCP) JSON-RPC 2.0 server and fast symbol search engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from groma import __version__
from groma.generators import generate_all_docs
from groma.graph import DependencyGraph
from groma.manifest import build_manifest, diff_manifests, load_manifest, save_manifest
from groma.parsers import build_file_index, load_file_index, save_file_index
from groma.scanner import scan_repository
from groma.schema import FileIndex, Manifest

MCP_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "groma_overview",
        "description": (
            "Return the repository's architectural overview, indexed languages, file counts, "
            "and top Core Hubs (most heavily imported files)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "groma_find_symbol",
        "description": (
            "Fast deterministic search across all indexed files, classes, methods, functions, "
            "database tables/seeders/migrations, and HTTP routes in the repository. "
            "Always call this tool BEFORE using bash 'find' or 'grep'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Symbol name, class, function, route path, or filename substring to find.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "groma_file_details",
        "description": (
            "Return the complete structural breakdown of a specific file (classes, methods, "
            "functions, HTTP routes, outgoing imports, and incoming dependents)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative POSIX path of the file in the repository.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "groma_impact_radius",
        "description": (
            "Compute the blast radius (all direct and transitive dependent files) affected "
            "if the specified file is modified or deleted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative POSIX path of the file being modified.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "groma_sync_status",
        "description": (
            "Check if the Groma index matches the current working tree on disk, and optionally "
            "run an incremental update to synchronize changed files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "auto_update": {
                    "type": "boolean",
                    "description": "If true and the index is stale, automatically re-parse changed files.",
                    "default": False,
                }
            },
        },
    },
]


def ensure_state_loaded(repo_root: Path) -> tuple[Manifest, FileIndex, DependencyGraph]:
    """Load Manifest and FileIndex from .groma/, or build them on the fly if missing."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root)
    file_index = load_file_index(repo_root)

    if manifest is None or file_index is None:
        scan_res = scan_repository(repo_root)
        manifest = build_manifest(repo_root, scan_res.files, scan_res.languages)
        file_index = build_file_index(repo_root, scan_res.files)
        graph = DependencyGraph(file_index)
        save_manifest(repo_root, manifest)
        save_file_index(repo_root, file_index)
        return manifest, file_index, graph

    return manifest, file_index, DependencyGraph(file_index)


def search_knowledge_base(file_index: FileIndex, query: str) -> list[dict[str, Any]]:
    """Search files, classes, methods, functions, and HTTP routes matching `query`."""
    q = query.strip().lower()
    if not q:
        return []

    matches: list[dict[str, Any]] = []

    for rel_path, analysis in sorted(file_index.files.items()):
        # 1. File path match
        if q in rel_path.lower():
            matches.append(
                {
                    "kind": "file",
                    "name": Path(rel_path).name,
                    "file": rel_path,
                    "line": 1,
                    "detail": f"{analysis.language} ({analysis.lines_of_code} lines)",
                }
            )

        # 2. Class & Method matches
        for cls in analysis.classes:
            if q in cls.name.lower():
                bases_str = f"({', '.join(cls.bases)})" if cls.bases else ""
                matches.append(
                    {
                        "kind": "class",
                        "name": cls.name,
                        "file": rel_path,
                        "line": cls.start_line,
                        "detail": f"class {cls.name}{bases_str} (lines {cls.start_line}-{cls.end_line})",
                    }
                )
            for m in cls.methods:
                if q in m.name.lower() or q in f"{cls.name}.{m.name}".lower():
                    sig = f"{cls.name}.{m.name}({', '.join(m.params)})"
                    matches.append(
                        {
                            "kind": "method",
                            "name": f"{cls.name}.{m.name}",
                            "file": rel_path,
                            "line": m.start_line,
                            "detail": f"{sig} (lines {m.start_line}-{m.end_line})",
                        }
                    )

        # 3. Top-level Function matches
        for fn in analysis.functions:
            if q in fn.name.lower():
                sig = f"{fn.name}({', '.join(fn.params)})"
                matches.append(
                    {
                        "kind": "function",
                        "name": fn.name,
                        "file": rel_path,
                        "line": fn.start_line,
                        "detail": f"{sig} (lines {fn.start_line}-{fn.end_line})",
                    }
                )

        # 4. HTTP Route matches
        for route in analysis.routes:
            if q in route.path.lower() or q in route.handler.lower() or q in route.method.lower():
                matches.append(
                    {
                        "kind": "route",
                        "name": f"{route.method} {route.path}",
                        "file": rel_path,
                        "line": route.line,
                        "detail": f"handler: {route.handler}",
                    }
                )

    return matches


def execute_mcp_tool(repo_root: Path, tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute one of Groma's MCP tools and return formatted text output."""
    repo_root = repo_root.resolve()

    if tool_name == "groma_overview":
        manifest, file_index, graph = ensure_state_loaded(repo_root)
        total_loc = sum(f.lines_of_code for f in file_index.files.values())
        hubs = graph.core_hubs(limit=10)
        hub_lines = [f"  - {p} (imported by {deg} files)" for p, deg in hubs] or ["  - None"]
        return "\n".join(
            [
                f"Project: {manifest.project_name}",
                f"Fingerprint: {manifest.fingerprint}",
                f"Tracked Files: {len(manifest.files)} ({total_loc:,} LOC)",
                f"Indexed Languages: {', '.join(manifest.languages) or 'None'}",
                "Core Hubs:",
                *hub_lines,
            ]
        )

    if tool_name == "groma_find_symbol":
        query = str(arguments.get("query", "")).strip()
        _, file_index, _ = ensure_state_loaded(repo_root)
        matches = search_knowledge_base(file_index, query)
        if not matches:
            return f"No files, symbols, or routes found matching '{query}'."
        lines = [f"Found {len(matches)} match(es) for '{query}':"]
        for m in matches[:50]:
            lines.append(f"- [{m['kind'].upper()}] {m['name']} -> {m['file']}:{m['line']} ({m['detail']})")
        return "\n".join(lines)

    if tool_name == "groma_file_details":
        target_path = str(arguments.get("path", "")).strip()
        _, file_index, graph = ensure_state_loaded(repo_root)
        analysis = file_index.files.get(target_path)
        if analysis is None:
            return f"File '{target_path}' is not in the Groma index."

        lines = [
            f"File: {analysis.path}",
            f"Language: {analysis.language} | Lines: {analysis.lines_of_code} | Size: {analysis.size} bytes",
            f"Imports ({len(graph.imports_of(target_path))}): {', '.join(graph.imports_of(target_path)) or 'None'}",
            f"Imported By ({len(graph.imported_by(target_path))}): {', '.join(graph.imported_by(target_path)) or 'None'}",
        ]
        if analysis.classes:
            lines.append("Classes:")
            for c in analysis.classes:
                methods_str = ", ".join(m.name for m in c.methods)
                lines.append(
                    f"  - class {c.name} (lines {c.start_line}-{c.end_line}) methods: [{methods_str}]"
                )
        if analysis.functions:
            lines.append("Functions:")
            for f in analysis.functions:
                lines.append(f"  - {f.name}({', '.join(f.params)}) (lines {f.start_line}-{f.end_line})")
        if analysis.routes:
            lines.append("Routes:")
            for r in analysis.routes:
                lines.append(f"  - {r.method} {r.path} -> {r.handler} (line {r.line})")
        return "\n".join(lines)

    if tool_name == "groma_impact_radius":
        target_path = str(arguments.get("path", "")).strip()
        _, file_index, graph = ensure_state_loaded(repo_root)
        impacted = graph.impact_radius([target_path])
        if not impacted:
            return f"No internal files depend on '{target_path}'."
        lines = [f"Impact Radius for '{target_path}' ({len(impacted)} dependent files):"]
        for dep in impacted:
            lines.append(f"  - {dep}")
        return "\n".join(lines)

    if tool_name == "groma_sync_status":
        auto_update = bool(arguments.get("auto_update", False))
        old_manifest, old_index, _ = ensure_state_loaded(repo_root)
        scan_res = scan_repository(repo_root)
        curr_manifest = build_manifest(
            repo_root,
            scan_res.files,
            scan_res.languages,
            previous_manifest=old_manifest,
            project_name=old_manifest.project_name,
        )
        diff = diff_manifests(old_manifest, curr_manifest)
        if diff.is_clean:
            return f"UP TO DATE (Fingerprint: {old_manifest.fingerprint})"

        if auto_update:
            new_index = build_file_index(
                repo_root,
                scan_res.files,
                previous_index=old_index,
                changed_files=set(diff.changed_files),
                project_name=old_manifest.project_name,
            )
            for d in diff.deleted:
                new_index.files.pop(d, None)
            graph = DependencyGraph(new_index)
            generate_all_docs(repo_root, curr_manifest, new_index, graph)
            save_manifest(repo_root, curr_manifest)
            save_file_index(repo_root, new_index)
            return (
                f"SYNCHRONIZED: Re-parsed {len(diff.changed_files)} changed file(s). "
                f"New Fingerprint: {curr_manifest.fingerprint}"
            )

        return (
            f"STALE: Modified={diff.modified}, Added={diff.added}, "
            f"Deleted={diff.deleted}, Renamed={diff.renamed}"
        )

    raise ValueError(f"Unknown MCP tool: {tool_name}")


def handle_mcp_request(repo_root: Path, request: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 request dictionary and return the response dictionary."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params") or {}

    # JSON-RPC Notifications have no 'id' and expect no response
    if req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "groma", "version": __version__},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS_SCHEMA},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            output_text = execute_mcp_tool(repo_root, tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": output_text}],
                    "isError": False,
                },
            }
        except (ValueError, OSError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_mcp_stdio_server(repo_root: Path) -> None:
    """Run the MCP JSON-RPC 2.0 server over standard input/output."""
    repo_root = repo_root.resolve()
    while True:
        line = sys.stdin.readline()
        if not line:
            break

        stripped = line.strip()
        if not stripped:
            continue

        # Support Content-Length header framing if used by client
        if stripped.lower().startswith("content-length:"):
            length = int(stripped.split(":", 1)[1].strip())
            # Consume blank header separator line
            sys.stdin.readline()
            body = sys.stdin.read(length)
            try:
                request = json.loads(body)
            except json.JSONDecodeError:
                continue
        else:
            try:
                request = json.loads(stripped)
            except json.JSONDecodeError:
                continue

        response = handle_mcp_request(repo_root, request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

