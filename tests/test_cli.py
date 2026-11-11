"""Integration tests for the Groma CLI commands: scan, check, and update."""

from pathlib import Path

from typer.testing import CliRunner

from groma.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """Verify --version option outputs version string."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Groma" in result.stdout


def test_cli_check_fails_without_baseline(tmp_path: Path) -> None:
    """Verify groma check returns code 1 if no baseline manifest exists."""
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 1
    assert "No Groma baseline found" in result.stdout


def test_cli_full_lifecycle_scan_check_update(tmp_path: Path) -> None:
    """Test full command lifecycle: scan -> check clean -> edit -> check stale -> update -> check clean."""
    # Setup a mini repository
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "db.py").write_text("def connect(): pass\n", encoding="utf-8")
    (app_dir / "auth.py").write_text("import app.db\ndef login(): pass\n", encoding="utf-8")
    (app_dir / "api.py").write_text("import app.auth\ndef handle(): pass\n", encoding="utf-8")

    # 1. groma scan
    res_scan = runner.invoke(app, ["scan", str(tmp_path)])
    assert res_scan.exit_code == 0
    assert "Baseline scan complete" in res_scan.stdout

    # Verify files created on disk
    assert (tmp_path / ".groma" / "manifest.json").is_file()
    assert (tmp_path / ".groma" / "file-index.json").is_file()
    assert (tmp_path / ".groma" / "architecture.md").is_file()
    assert (tmp_path / ".groma" / "file-map.md").is_file()
    assert (tmp_path / ".groma" / "dependencies.md").is_file()

    # 2. groma check (clean)
    res_check_clean = runner.invoke(app, ["check", str(tmp_path)])
    assert res_check_clean.exit_code == 0
    assert "UP TO DATE" in res_check_clean.stdout

    # 3. Modify db.py
    (app_dir / "db.py").write_text("def connect_v2(): return 42\n", encoding="utf-8")

    # 4. groma check (stale)
    res_check_stale = runner.invoke(app, ["check", str(tmp_path)])
    assert res_check_stale.exit_code == 1
    assert "STALE" in res_check_stale.stdout
    assert "app/db.py" in res_check_stale.stdout
    # Impact radius: app/auth.py and app/api.py depend directly/transitively on app/db.py
    assert "app/auth.py" in res_check_stale.stdout
    assert "app/api.py" in res_check_stale.stdout

    # 5. groma update
    res_update = runner.invoke(app, ["update", str(tmp_path)])
    assert res_update.exit_code == 0
    assert "SYNCHRONIZED" in res_update.stdout

    # 6. groma check (clean again)
    res_check_post_update = runner.invoke(app, ["check", str(tmp_path)])
    assert res_check_post_update.exit_code == 0
    assert "UP TO DATE" in res_check_post_update.stdout


def test_cli_update_when_clean(tmp_path: Path) -> None:
    """Verify groma update reports already up to date when clean."""
    (tmp_path / "main.py").write_text("print('clean')\n", encoding="utf-8")
    runner.invoke(app, ["scan", str(tmp_path)])

    res_update = runner.invoke(app, ["update", str(tmp_path)])
    assert res_update.exit_code == 0
    assert "already up to date" in res_update.stdout


def test_cli_register_command() -> None:
    """Verify groma register command executes and resolves executable."""
    result = runner.invoke(app, ["register"])
    assert result.exit_code == 0
    assert "Resolved Groma executable" in result.stdout


