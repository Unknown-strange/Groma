"""Tests for MCP multi-IDE registration."""

from pathlib import Path

from groma.mcp_registry import _update_json_mcp_config, find_groma_executable


def test_find_groma_executable() -> None:
    """Verify executable resolver returns a non-empty string."""
    exe = find_groma_executable()
    assert isinstance(exe, str)
    assert len(exe) > 0


def test_update_json_mcp_config_creates_and_updates(tmp_path: Path) -> None:
    """Verify MCP JSON configuration creation and safe updates."""
    cfg_file = tmp_path / "sub" / "mcp_servers.json"

    # 1. Create new
    status, msg = _update_json_mcp_config(
        cfg_file,
        "groma",
        {"command": "/usr/local/bin/groma", "args": ["mcp", "."]},
    )
    assert status == "registered"
    assert "Successfully" in msg
    assert cfg_file.is_file()

    # 2. Update existing
    status, msg = _update_json_mcp_config(
        cfg_file,
        "groma",
        {"command": "/custom/path/groma", "args": ["mcp", "."]},
    )
    assert status == "updated"

    # Verify content
    content = cfg_file.read_text(encoding="utf-8")
    assert "/custom/path/groma" in content

    # 3. Handle 0-byte empty file safely
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("   \n", encoding="utf-8")
    status_empty, msg_empty = _update_json_mcp_config(
        empty_file,
        "groma",
        {"command": "/usr/local/bin/groma", "args": ["mcp", "."]},
    )
    assert status_empty == "registered"
    assert "Successfully" in msg_empty

