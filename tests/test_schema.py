"""Unit tests for Groma's unified Pydantic data contract (groma/schema.py)."""

from groma.schema import (
    ClassInfo,
    DiffResult,
    FileAnalysis,
    FileHashEntry,
    FileIndex,
    FunctionInfo,
    Manifest,
    RouteInfo,
)


def test_manifest_round_trip_serialization() -> None:
    """Verify Manifest and FileHashEntry serialize to JSON and deserialize identically."""
    entry = FileHashEntry(
        hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        size=1024,
        mtime=1700000000.5,
        language="python",
    )
    manifest = Manifest(
        project_name="demo-repo",
        fingerprint="abc123fingerprint",
        frameworks=["FastAPI", "React"],
        files={"app/main.py": entry},
    )

    raw_json = manifest.model_dump_json(indent=2)
    restored = Manifest.model_validate_json(raw_json)

    assert restored.project_name == "demo-repo"
    assert restored.fingerprint == "abc123fingerprint"
    assert restored.frameworks == ["FastAPI", "React"]
    assert "app/main.py" in restored.files
    assert restored.files["app/main.py"].size == 1024
    assert restored.files["app/main.py"].language == "python"


def test_diff_result_is_clean_and_changed_files() -> None:
    """Verify DiffResult.is_clean and DiffResult.changed_files properties."""
    clean_diff = DiffResult(unchanged=["app/main.py", "app/utils.py"])
    assert clean_diff.is_clean is True
    assert clean_diff.changed_files == []

    dirty_diff = DiffResult(
        added=["app/new.py"],
        modified=["app/main.py"],
        deleted=["app/old.py"],
        renamed={"app/legacy.py": "app/modern.py"},
        unchanged=["app/utils.py"],
    )
    assert dirty_diff.is_clean is False
    assert dirty_diff.changed_files == ["app/main.py", "app/modern.py", "app/new.py"]


def test_file_analysis_and_file_index_round_trip() -> None:
    """Verify FileAnalysis, ClassInfo, FunctionInfo, RouteInfo, and FileIndex round-trip."""
    method = FunctionInfo(
        name="authenticate",
        params=["self", "token: str"],
        return_type="bool",
        decorators=["@staticmethod"],
        docstring="Validate a user bearer token.",
        start_line=15,
        end_line=25,
        is_async=True,
        calls=["decode_jwt", "check_expiry"],
    )

    cls_info = ClassInfo(
        name="AuthService",
        bases=["BaseService"],
        decorators=["@singleton"],
        docstring="Handles user authentication.",
        start_line=10,
        end_line=30,
        methods=[method],
    )

    route = RouteInfo(
        method="POST",
        path="/api/v1/login",
        handler="login_user",
        line=35,
    )

    top_func = FunctionInfo(
        name="login_user",
        params=["payload: LoginRequest"],
        return_type="TokenResponse",
        decorators=['@router.post("/api/v1/login")'],
        docstring="Login endpoint handler.",
        start_line=35,
        end_line=48,
        is_async=True,
        calls=["AuthService.authenticate"],
    )

    analysis = FileAnalysis(
        path="app/auth.py",
        language="python",
        size=2048,
        lines_of_code=50,
        module_docstring="Authentication module.",
        imports=["jwt", "app.models.LoginRequest"],
        classes=[cls_info],
        functions=[top_func],
        routes=[route],
    )

    index = FileIndex(
        project_name="demo-repo",
        files={"app/auth.py": analysis},
    )

    raw_json = index.model_dump_json(indent=2)
    restored = FileIndex.model_validate_json(raw_json)

    restored_file = restored.files["app/auth.py"]
    assert restored_file.language == "python"
    assert restored_file.lines_of_code == 50
    assert len(restored_file.classes) == 1
    assert restored_file.classes[0].name == "AuthService"
    assert restored_file.classes[0].methods[0].is_async is True
    assert len(restored_file.routes) == 1
    assert restored_file.routes[0].method == "POST"
    assert restored_file.routes[0].path == "/api/v1/login"

