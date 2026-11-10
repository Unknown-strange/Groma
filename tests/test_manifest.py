"""Unit tests for Groma's SHA-256 manifest builder, fast cache check, and diff engine."""

from pathlib import Path
from unittest.mock import patch

from groma.manifest import (
    build_manifest,
    compute_file_sha256,
    diff_manifests,
    load_manifest,
    save_manifest,
)
from groma.scanner import scan_repository


def test_build_manifest_and_fast_cache_reuse(tmp_path: Path) -> None:
    """Verify build_manifest hashes files and reuses cached hashes when size & mtime match."""
    file_a = tmp_path / "a.py"
    file_a.write_text("def alpha(): return 1\n", encoding="utf-8")

    scan = scan_repository(tmp_path)
    manifest_1 = build_manifest(tmp_path, scan.files, scan.frameworks, project_name="test-proj")

    assert "a.py" in manifest_1.files
    assert manifest_1.files["a.py"].hash == compute_file_sha256(file_a)

    # Rebuild with previous_manifest; compute_file_sha256 should NOT be called for unchanged file
    with patch("groma.manifest.compute_file_sha256") as mock_hash:
        manifest_2 = build_manifest(
            tmp_path,
            scan.files,
            scan.frameworks,
            previous_manifest=manifest_1,
            project_name="test-proj",
        )
        mock_hash.assert_not_called()

    assert manifest_2.fingerprint == manifest_1.fingerprint


def test_diff_manifests_added_modified_deleted_renamed_unchanged(tmp_path: Path) -> None:
    """Verify diff_manifests accurately classifies all 5 change categories including renames."""
    (tmp_path / "unchanged.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "modified.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "deleted.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / "old_name.py").write_text("def move_me(): pass\n", encoding="utf-8")

    scan_1 = scan_repository(tmp_path)
    manifest_1 = build_manifest(tmp_path, scan_1.files)

    # Apply changes on disk:
    # 1. Modify modified.py
    (tmp_path / "modified.py").write_text("y = 2\n", encoding="utf-8")
    # 2. Delete deleted.py
    (tmp_path / "deleted.py").unlink()
    # 3. Rename old_name.py -> new_name.py (identical content -> identical SHA-256)
    (tmp_path / "old_name.py").rename(tmp_path / "new_name.py")
    # 4. Add brand_new.py
    (tmp_path / "brand_new.py").write_text("w = 99\n", encoding="utf-8")

    scan_2 = scan_repository(tmp_path)
    manifest_2 = build_manifest(tmp_path, scan_2.files)

    diff = diff_manifests(manifest_1, manifest_2)

    assert diff.is_clean is False
    assert diff.unchanged == ["unchanged.py"]
    assert diff.modified == ["modified.py"]
    assert diff.deleted == ["deleted.py"]
    assert diff.renamed == {"old_name.py": "new_name.py"}
    assert diff.added == ["brand_new.py"]


def test_save_and_load_manifest_persistence(tmp_path: Path) -> None:
    """Verify .groma/manifest.json saves and loads cleanly."""
    assert load_manifest(tmp_path) is None

    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    scan = scan_repository(tmp_path)
    manifest = build_manifest(tmp_path, scan.files, frameworks=["FastAPI"])

    saved_path = save_manifest(tmp_path, manifest)
    assert saved_path == (tmp_path / ".groma" / "manifest.json").resolve()
    assert saved_path.is_file()

    loaded = load_manifest(tmp_path)
    assert loaded is not None
    assert loaded.fingerprint == manifest.fingerprint
    assert loaded.frameworks == ["FastAPI"]
    assert "app.py" in loaded.files

