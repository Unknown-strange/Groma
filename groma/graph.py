"""Dependency graph, cross-language import resolution, core hub detection, and impact radius."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PurePosixPath

import networkx as nx

from groma.schema import FileIndex


def _build_module_lookup(files: list[str]) -> dict[str, str]:
    """Map candidate module/namespace/path keys to relative POSIX file paths.

    Supports:
      - Python dotted modules ('groma/scanner.py' -> 'groma.scanner')
      - PHP PSR-4 namespaces ('app/Models/User.php' -> 'app.models.user', 'App\\Models\\User')
      - JS/TS/Vue paths & index files ('src/components/Header.vue' -> 'src/components/Header')
    """
    lookup: dict[str, str] = {}

    for rel_path in files:
        p = Path(rel_path)
        no_ext = p.with_suffix("")
        parts = list(no_ext.parts)
        if not parts:
            continue

        # Handle Python __init__.py and JS/TS index.(js|ts|tsx|jsx)
        if parts[-1] in ("__init__", "index"):
            parts = parts[:-1]
            if not parts:
                continue
            lookup["/".join(parts)] = rel_path

        # 1. Exact POSIX path without extension (for JS/TS imports)
        posix_no_ext = no_ext.as_posix()
        lookup[posix_no_ext] = rel_path
        lookup[posix_no_ext.lower()] = rel_path
        lookup[rel_path] = rel_path

        # 2. Full dotted path (e.g. 'groma.scanner' or 'app.Models.User')
        full_dot = ".".join(parts)
        lookup[full_dot] = rel_path
        lookup[full_dot.lower()] = rel_path

        # 3. Common source roots ('src/', 'lib/', 'app/', 'frontend/src/', 'backend/app/')
        if len(parts) > 1 and parts[0] in ("src", "lib", "app"):
            sub_dot = ".".join(parts[1:])
            sub_posix = "/".join(parts[1:])
            lookup[sub_dot] = rel_path
            lookup[sub_dot.lower()] = rel_path
            lookup[sub_posix] = rel_path
            lookup[sub_posix.lower()] = rel_path
        if len(parts) > 2 and parts[1] in ("src", "app"):
            sub_dot2 = ".".join(parts[2:])
            sub_posix2 = "/".join(parts[2:])
            lookup[sub_dot2] = rel_path
            lookup[sub_dot2.lower()] = rel_path
            lookup[sub_posix2] = rel_path
            lookup[sub_posix2.lower()] = rel_path
            # Also register from parts[1:] (e.g. backend/app/Models/User.php -> app.models.user)
            sub_dot1 = ".".join(parts[1:])
            lookup[sub_dot1] = rel_path
            lookup[sub_dot1.lower()] = rel_path

    return lookup


def _resolve_import_target(
    source_path: str, raw_import: str, module_lookup: dict[str, str]
) -> str | None:
    """Resolve a single raw import string from `source_path` to a tracked repository file."""
    imp = raw_import.strip()
    if not imp:
        return None

    # 1. Relative JS/TS/Vue path imports: './foo' or '../bar/baz'
    if imp.startswith("."):
        base_dir = PurePosixPath(source_path).parent
        norm_parts: list[str] = list(base_dir.parts) if str(base_dir) != "." else []
        for seg in imp.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if norm_parts:
                    norm_parts.pop()
            else:
                norm_parts.append(seg)
        rel_candidate = "/".join(norm_parts)
        target = module_lookup.get(rel_candidate) or module_lookup.get(rel_candidate.lower())
        if target:
            return target

    # 2. Alias imports in JS/TS/Vue: '@/components/Btn' or '~/utils/api'
    if imp.startswith(("@/", "~/")):
        stripped = imp[2:]
        target = module_lookup.get(stripped) or module_lookup.get(stripped.lower())
        if target:
            return target

    # 3. PHP namespace imports ('App\\Models\\User') or dotted Python imports ('groma.schema')
    normalized = imp.replace("\\", ".").replace("/", ".").strip(".")
    parts = [p for p in normalized.split(".") if p]

    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        target = module_lookup.get(prefix) or module_lookup.get(prefix.lower())
        if target is not None:
            return target

    return None


class DependencyGraph:
    """Directed dependency graph representing internal codebase dependencies.

    A directed edge `u -> v` means file `u` imports file `v`.
    """

    def __init__(self, file_index: FileIndex) -> None:
        self.file_index = file_index
        self.graph = nx.DiGraph()
        self._build_graph()

    def _build_graph(self) -> None:
        """Construct the NetworkX DiGraph by resolving imports across all files in the index."""
        all_paths = sorted(self.file_index.files.keys())
        for path in all_paths:
            self.graph.add_node(path)

        module_lookup = _build_module_lookup(all_paths)

        for source_path, analysis in self.file_index.files.items():
            resolved_targets: set[str] = set()

            for raw_import in analysis.imports:
                target_file = _resolve_import_target(source_path, raw_import, module_lookup)
                if target_file is not None and target_file != source_path:
                    resolved_targets.add(target_file)

            for target in sorted(resolved_targets):
                self.graph.add_edge(source_path, target)

    def imports_of(self, file_path: str) -> list[str]:
        """Return files directly imported by `file_path` (outgoing edges / successors)."""
        if file_path not in self.graph:
            return []
        return sorted(self.graph.successors(file_path))

    def imported_by(self, file_path: str) -> list[str]:
        """Return files that directly import `file_path` (incoming edges / predecessors)."""
        if file_path not in self.graph:
            return []
        return sorted(self.graph.predecessors(file_path))

    def core_hubs(self, limit: int = 10) -> list[tuple[str, int]]:
        """Return the most heavily imported files (highest in-degree / Fan-In).

        Only files with at least 1 incoming import (in_degree > 0) are returned,
        sorted in descending order of in-degree, then alphabetically by path.
        """
        scored: list[tuple[str, int]] = []
        for node in self.graph.nodes:
            in_deg = self.graph.in_degree(node)
            if in_deg > 0:
                scored.append((node, in_deg))

        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    def impact_radius(self, changed_files: list[str]) -> list[str]:
        """Return all files that directly or transitively depend on any of `changed_files`.

        Since `u -> v` means `u` imports `v`, any node `u` that has a directed path
        to `v` (`nx.ancestors(graph, v)`) is affected when `v` changes.
        """
        impacted: set[str] = set()
        changed_set = set(changed_files)

        for target in changed_files:
            if target in self.graph:
                ancestors = nx.ancestors(self.graph, target)
                impacted.update(ancestors)

        return sorted(impacted - changed_set)

    def to_dict(self) -> dict[str, dict[str, list[str]]]:
        """Serialize the dependency structure into a JSON-friendly mapping."""
        res: dict[str, dict[str, list[str]]] = defaultdict(dict)
        for node in sorted(self.graph.nodes):
            res[node] = {
                "imports": self.imports_of(node),
                "imported_by": self.imported_by(node),
            }
        return dict(res)
