"""Unit tests for Groma's markdown and SKILL.md document generators."""

from pathlib import Path

from groma.generators import generate_all_docs
from groma.generators.markdown import (
    generate_architecture_doc,
    generate_dependencies_doc,
    generate_file_map_doc,
)
from groma.generators.skill import generate_skill_doc
from groma.graph import DependencyGraph
from groma.schema import (
    ClassInfo,
    FileAnalysis,
    FileHashEntry,
    FileIndex,
    FunctionInfo,
    Manifest,
    RouteInfo,
)


def _sample_fixtures() -> tuple[Manifest, FileIndex, DependencyGraph]:
    """Create sample Manifest, FileIndex, and DependencyGraph for generator testing."""
    manifest = Manifest(
        project_name="my-service",
        fingerprint="abcd1234ef567890",
        languages=["php", "python"],
        files={
            "app/main.py": FileHashEntry(hash="h1", size=500, mtime=100.0, language="python"),
            "app/auth.py": FileHashEntry(hash="h2", size=800, mtime=100.0, language="python"),
        },
    )

    func = FunctionInfo(
        name="verify_token",
        params=["token: str", "secret: str = 'def'"],
        return_type="bool",
        decorators=["@cache"],
        docstring="Verify user token.",
        start_line=10,
        end_line=15,
        is_async=False,
        calls=["decode"],
    )

    cls = ClassInfo(
        name="AuthManager",
        bases=["BaseAuth"],
        decorators=[],
        docstring="Authentication manager.",
        start_line=20,
        end_line=30,
        methods=[func],
    )

    route = RouteInfo(
        method="POST",
        path="/login",
        handler="login_handler",
        line=35,
    )

    route_func = FunctionInfo(
        name="login_handler",
        params=[],
        return_type=None,
        decorators=['@app.post("/login")'],
        docstring="Login endpoint.",
        start_line=35,
        end_line=40,
        is_async=True,
    )

    file_index = FileIndex(
        project_name="my-service",
        files={
            "app/auth.py": FileAnalysis(
                path="app/auth.py",
                language="python",
                size=800,
                lines_of_code=40,
                module_docstring="Auth module.",
                classes=[cls],
                functions=[],
            ),
            "app/main.py": FileAnalysis(
                path="app/main.py",
                language="python",
                size=500,
                lines_of_code=25,
                module_docstring="Main app.",
                imports=["app.auth"],
                functions=[route_func],
                routes=[route],
            ),
        },
    )

    graph = DependencyGraph(file_index)
    return manifest, file_index, graph


def test_generate_architecture_doc() -> None:
    """Verify architecture.md includes overview, languages, hubs, and route table."""
    manifest, file_index, graph = _sample_fixtures()
    doc = generate_architecture_doc(manifest, file_index, graph)

    assert "# my-service — System Architecture & Core Map" in doc
    assert "`php`" in doc
    assert "`python`" in doc
    assert "`app/auth.py`" in doc  # Hub imported by main.py
    assert "| `POST` | `/login` | `login_handler` | `app/main.py:35` |" in doc


def test_generate_file_map_doc() -> None:
    """Verify file-map.md documents classes, functions, and lines."""
    _, file_index, _ = _sample_fixtures()
    doc = generate_file_map_doc(file_index)

    assert "## `app/auth.py`" in doc
    assert "class AuthManager(BaseAuth)" in doc
    assert "def verify_token(token: str, secret: str = 'def') -> bool" in doc
    assert "## `app/main.py`" in doc
    assert "async def login_handler()" in doc


def test_generate_dependencies_doc() -> None:
    """Verify dependencies.md documents internal imports and imported_by."""
    _, _, graph = _sample_fixtures()
    doc = generate_dependencies_doc(graph)

    assert "### `app/main.py`" in doc
    assert "- `app/auth.py`" in doc
    assert "### `app/auth.py`" in doc
    assert "**Imported By (1 Dependents):**" in doc


def test_generate_skill_doc() -> None:
    """Verify SKILL.md YAML frontmatter and rules."""
    manifest, _, _ = _sample_fixtures()
    doc = generate_skill_doc(manifest)

    assert "name: my-service-knowledge" in doc
    assert "fingerprint: abcd1234ef567890" in doc
    assert "groma check" in doc
    assert "groma update" in doc
    assert ".groma/architecture.md" in doc


def test_generate_all_docs_on_disk(tmp_path: Path) -> None:
    """Verify render_all_docs creates markdown, skill, rule, and MCP config files on disk."""
    manifest, file_index, graph = _sample_fixtures()
    paths = generate_all_docs(tmp_path, manifest, file_index, graph)

    assert len(paths) == 8
    for p in paths:
        assert p.is_file()

    assert (tmp_path / ".groma" / "architecture.md").is_file()
    assert (tmp_path / ".groma" / "file-map.md").is_file()
    assert (tmp_path / ".groma" / "dependencies.md").is_file()
    assert (tmp_path / ".agents" / "skills" / "my-service-knowledge" / "SKILL.md").is_file()
    assert (tmp_path / ".agents" / "rules" / "groma-sync.md").is_file()
    assert (tmp_path / ".cursorrules").is_file()
    assert (tmp_path / ".mcp.json").is_file()
    assert (tmp_path / ".cursor" / "mcp.json").is_file()

