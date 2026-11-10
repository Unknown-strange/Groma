"""Dependency graph, import resolution, core hub detection, and impact radius analysis."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import networkx as nx

from groma.schema import FileIndex


def _build_module_lookup(files: list[str]) -> dict[str, str]:
    """Map candidate dotted module paths to relative POSIX file paths.

    Examples:
      - 'groma/scanner.py' -> 'groma.scanner'
      - 'groma/__init__.py' -> 'groma'
      - 'src/app/auth.py' -> 'src.app.auth' and 'app.auth'
    """
    lookup: dict[str, str] = {}

    for rel_path in files:
        p = Path(rel_path)
        # Drop extension for code files
        parts = list(p.with_suffix("").parts)
        if not parts:
            continue

        # If it's an __init__ file, the package itself is the module
        if parts[-1] == "__init__":
            parts = parts[:-1]
            if not parts:
                continue

        # 1. Full dotted path: e.g. src.app.auth
        full_dot = ".".join(parts)
        lookup[full_dot] = rel_path

        # 2. If path starts with common root markers like 'src' or 'lib', also register sub-path
        if len(parts) > 1 and parts[0] in ("src", "lib", "app"):
            sub_dot = ".".join(parts[1:])
            lookup[sub_dot] = rel_path

    return lookup


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
                # Walk down the import dotted path to find the longest matching module
                # e.g., 'groma.schema.Manifest' -> test 'groma.schema.Manifest' then 'groma.schema'
                parts = raw_import.split(".")
                for i in range(len(parts), 0, -1):
                    prefix = ".".join(parts[:i])
                    target_file = module_lookup.get(prefix)
                    if target_file is not None:
                        if target_file != source_path:
                            resolved_targets.add(target_file)
                        break

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
                # nx.ancestors returns all nodes that have a directed path leading to target
                ancestors = nx.ancestors(self.graph, target)
                impacted.update(ancestors)

        # Exclude the changed files themselves from their own dependent impact list
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

