"""Unit tests for Groma's Python AST parser and file-index cache."""

from pathlib import Path

from groma.parsers import build_file_index, load_file_index, save_file_index
from groma.parsers.python_ast import parse_python_file


def test_parse_python_classes_functions_and_calls(tmp_path: Path) -> None:
    """Verify AST extraction of classes, methods, functions, type hints, and calls."""
    code = '''"""Module docstring summary."""

from typing import Optional

def helper(x: int = 10) -> int:
    """Calculate something."""
    return x * 2

class UserManager:
    """Manages system users."""

    def __init__(self, db_url: str):
        self.db_url = db_url

    async def get_user(self, user_id: int, active: bool = True) -> Optional[dict]:
        """Fetch user by id."""
        val = helper(user_id)
        return {"id": user_id, "active": active, "val": val}
'''
    py_file = tmp_path / "user.py"
    py_file.write_text(code, encoding="utf-8")

    analysis = parse_python_file(tmp_path, "user.py")

    assert analysis.path == "user.py"
    assert analysis.language == "python"
    assert analysis.module_docstring == "Module docstring summary."
    assert "typing.Optional" in analysis.imports

    # Functions
    assert len(analysis.functions) == 1
    top_func = analysis.functions[0]
    assert top_func.name == "helper"
    assert top_func.params == ["x: int = 10"]
    assert top_func.return_type == "int"
    assert top_func.docstring == "Calculate something."
    assert top_func.is_async is False

    # Classes
    assert len(analysis.classes) == 1
    cls = analysis.classes[0]
    assert cls.name == "UserManager"
    assert cls.docstring == "Manages system users."
    assert len(cls.methods) == 2

    init_method = cls.methods[0]
    assert init_method.name == "__init__"
    assert init_method.params == ["self", "db_url: str"]

    async_method = cls.methods[1]
    assert async_method.name == "get_user"
    assert async_method.is_async is True
    assert "helper" in async_method.calls


def test_parse_http_routes(tmp_path: Path) -> None:
    """Verify route extraction for FastAPI, Flask, and router decorators."""
    code = '''
from fastapi import APIRouter

router = APIRouter()

@router.get("/users/{user_id}")
async def read_user(user_id: int):
    return {"user_id": user_id}

@router.post(path="/auth/login")
def login():
    pass

@app.route("/metrics", methods=["GET", "POST"])
def get_metrics():
    pass
'''
    (tmp_path / "api.py").write_text(code, encoding="utf-8")

    analysis = parse_python_file(tmp_path, "api.py")

    assert len(analysis.routes) == 4
    route_map = {(r.method, r.path): r.handler for r in analysis.routes}

    assert route_map[("GET", "/users/{user_id}")] == "read_user"
    assert route_map[("POST", "/auth/login")] == "login"
    assert route_map[("GET", "/metrics")] == "get_metrics"
    assert route_map[("POST", "/metrics")] == "get_metrics"


def test_syntax_error_resilience(tmp_path: Path) -> None:
    """Verify parser returns basic stats without raising an exception on invalid syntax."""
    (tmp_path / "broken.py").write_text("def broken_func(\n", encoding="utf-8")

    analysis = parse_python_file(tmp_path, "broken.py")

    assert analysis.path == "broken.py"
    assert analysis.language == "python"
    assert analysis.lines_of_code == 1
    assert analysis.classes == []
    assert analysis.functions == []


def test_file_index_building_and_caching(tmp_path: Path) -> None:
    """Verify build_file_index, incremental reuse, and save/load file-index.json."""
    (tmp_path / "a.py").write_text("def fa(): pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def fb(): pass\n", encoding="utf-8")

    scanned = [("a.py", "python"), ("b.py", "python")]
    idx1 = build_file_index(tmp_path, scanned, project_name="demo")

    assert "a.py" in idx1.files
    assert "b.py" in idx1.files

    # Save to disk
    save_path = save_file_index(tmp_path, idx1)
    assert save_path.is_file()

    # Load from disk
    loaded = load_file_index(tmp_path)
    assert loaded is not None
    assert loaded.project_name == "demo"
    assert "a.py" in loaded.files

    # Incremental update: modify b.py, reuse cached a.py
    (tmp_path / "b.py").write_text("def fb_v2(): pass\n", encoding="utf-8")
    idx2 = build_file_index(tmp_path, scanned, previous_index=idx1, changed_files={"b.py"})

    # a.py object instance is reused
    assert idx2.files["a.py"] is idx1.files["a.py"]
    # b.py is re-parsed with new function name
    assert idx2.files["b.py"].functions[0].name == "fb_v2"
