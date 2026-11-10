"""Unit tests for Groma's NetworkX dependency graph and impact radius engine."""

from groma.graph import DependencyGraph, _build_module_lookup
from groma.schema import FileAnalysis, FileIndex


def test_build_module_lookup() -> None:
    """Verify conversion of file paths to dotted module candidates."""
    files = [
        "groma/scanner.py",
        "groma/__init__.py",
        "src/app/auth.py",
        "src/app/services/__init__.py",
    ]
    lookup = _build_module_lookup(files)

    assert lookup["groma.scanner"] == "groma/scanner.py"
    assert lookup["groma"] == "groma/__init__.py"
    assert lookup["src.app.auth"] == "src/app/auth.py"
    assert lookup["app.auth"] == "src/app/auth.py"
    assert lookup["app.services"] == "src/app/services/__init__.py"


def test_dependency_graph_edges_hubs_and_impact() -> None:
    """Verify directed edge creation, core hubs ranking, and transitive impact radius.

    Dependency chain:
      service.py -> auth.py -> db.py
      api     -> auth.py
      standalone.py (isolated)
    """


    file_index = FileIndex(
        project_name="test-repo",
        files={
            "app/db.py": FileAnalysis(
                path="app/db.py",
                language="python",
                imports=[],
            ),
            "app/auth.py": FileAnalysis(
                path="app/auth.py",
                language="python",
                imports=["app.db", "app.db.connect"],
            ),
            "app/service.py": FileAnalysis(
                path="app/service.py",
                language="python",
                imports=["app.auth.verify_token"],
            ),
            "app/api.py": FileAnalysis(
                path="app/api.py",
                language="python",
                imports=["app.auth.verify_token"],
            ),
            "app/standalone.py": FileAnalysis(
                path="app/standalone.py",
                language="python",
                imports=["os", "json"],
            ),
        },
    )

    dep_graph = DependencyGraph(file_index)

    # Edge inspections
    assert dep_graph.imports_of("app/service.py") == ["app/auth.py"]
    assert dep_graph.imports_of("app/auth.py") == ["app/db.py"]
    assert dep_graph.imported_by("app/auth.py") == ["app/api.py", "app/service.py"]
    assert dep_graph.imports_of("app/standalone.py") == []

    # Core Hubs: auth.py (imported by 2 files), db.py (imported by 1 file)
    hubs = dep_graph.core_hubs()
    assert hubs == [("app/auth.py", 2), ("app/db.py", 1)]

    # Transitive Impact Radius:
    # If app/db.py changes, it impacts direct dependent auth.py AND transitive dependents service.py + api.py
    impact_db = dep_graph.impact_radius(["app/db.py"])
    assert impact_db == ["app/api.py", "app/auth.py", "app/service.py"]

    # If app/auth.py changes, it impacts service.py and api.py
    impact_auth = dep_graph.impact_radius(["app/auth.py"])
    assert impact_auth == ["app/api.py", "app/service.py"]

    # If standalone changes, impact is empty
    assert dep_graph.impact_radius(["app/standalone.py"]) == []

