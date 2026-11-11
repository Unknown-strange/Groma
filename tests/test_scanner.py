"""Unit tests for Groma's universal repository scanner, .gitignore filter, and dependency exclusions."""

from pathlib import Path

from groma.scanner import is_dependency_file, scan_repository


def test_ignores_all_gitignore_files_and_directories(tmp_path: Path) -> None:
    """Verify every file and folder matched by .gitignore is ignored."""
    (tmp_path / ".gitignore").write_text(
        "ignored_dir/\n*.secret.py\nspecific_ignored.py\nbuild_output/*\n",
        encoding="utf-8",
    )

    # Valid source files
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.ts").write_text("export const x = 1;", encoding="utf-8")

    # Files that match .gitignore
    ignored_dir = tmp_path / "ignored_dir"
    ignored_dir.mkdir()
    (ignored_dir / "inside.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "auth.secret.py").write_text("secret = 123", encoding="utf-8")
    (tmp_path / "specific_ignored.py").write_text("y = 2", encoding="utf-8")
    build_dir = tmp_path / "build_output"
    build_dir.mkdir()
    (build_dir / "generated.js").write_text("var a = 1;", encoding="utf-8")

    result = scan_repository(tmp_path)
    assert result.files == [
        ("main.py", "python"),
        ("src/app.ts", "typescript"),
    ]
    assert result.languages == ["python", "typescript"]


def test_ignores_dependency_files_and_folders_across_projects(tmp_path: Path) -> None:
    """Verify dependency manifests, lockfiles, and vendor/venv dirs are never tracked."""
    # Actual source code
    (tmp_path / "service.py").write_text("def run(): pass", encoding="utf-8")
    (tmp_path / "index.js").write_text("console.log(1);", encoding="utf-8")

    # Python dependency files & folders
    (tmp_path / "requirements.txt").write_text("fastapi==0.110.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest==8.0.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (tmp_path / "setup.py").write_text("from setuptools import setup; setup()", encoding="utf-8")
    (tmp_path / "Pipfile").write_text("[packages]", encoding="utf-8")
    (tmp_path / "poetry.lock").write_text("lock", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock", encoding="utf-8")

    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "site.py").write_text("# third party", encoding="utf-8")

    # JS / TS dependency files & folders
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "yarn.lock").write_text("# yarn", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 6", encoding="utf-8")

    node_modules = tmp_path / "node_modules" / "react"
    node_modules.mkdir(parents=True)
    (node_modules / "index.js").write_text("module.exports = {};", encoding="utf-8")

    # Other ecosystems (Go, Rust, PHP, Ruby)
    (tmp_path / "go.mod").write_text("module example.com/m", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")
    vendor_dir = tmp_path / "vendor" / "pkg"
    vendor_dir.mkdir(parents=True)
    (vendor_dir / "lib.py").write_text("pass", encoding="utf-8")

    # Non-code assets (images, markdown)
    (tmp_path / "diagram.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")

    result = scan_repository(tmp_path)

    # Only actual source code files are tracked; setup.py and all dependency files are excluded
    assert result.files == [
        ("index.js", "javascript"),
        ("service.py", "python"),
    ]
    assert is_dependency_file("setup.py") is True
    assert is_dependency_file("requirements-prod.txt") is True
    assert is_dependency_file("package-lock.json") is True


def test_full_stack_multi_language_indexing(tmp_path: Path) -> None:
    """Verify PHP, Vue, TypeScript, SQL, YAML, Go, and Rust files are all indexed."""
    (tmp_path / "UsersTableSeeder.php").write_text("<?php class UsersTableSeeder {}", encoding="utf-8")
    (tmp_path / "Dashboard.vue").write_text("<script setup></script>", encoding="utf-8")
    (tmp_path / "schema.sql").write_text("CREATE TABLE users (id INT);", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  db:\n    image: mysql:8", encoding="utf-8")
    (tmp_path / "server.go").write_text("package main", encoding="utf-8")
    (tmp_path / "lib.rs").write_text("pub struct Engine;", encoding="utf-8")

    result = scan_repository(tmp_path)
    assert result.languages == ["go", "php", "rust", "sql", "vue", "yaml"]
    assert ("UsersTableSeeder.php", "php") in result.files
    assert ("Dashboard.vue", "vue") in result.files
    assert ("schema.sql", "sql") in result.files
    assert ("docker-compose.yml", "yaml") in result.files
