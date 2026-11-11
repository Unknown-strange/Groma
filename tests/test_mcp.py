"""Unit and integration tests for Groma's MCP server and `groma find` CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from groma.cli import app
from groma.mcp_server import handle_mcp_request

runner = CliRunner()


def test_mcp_initialize_tools_list_and_calls(tmp_path: Path) -> None:
    """Verify MCP JSON-RPC initialize, tools/list, and tools/call across a full-stack repo."""
    seeder_dir = tmp_path / "database" / "seeders"
    seeder_dir.mkdir(parents=True)
    (seeder_dir / "UsersTableSeeder.php").write_text(
        """<?php
class UsersTableSeeder extends Seeder
{
    public function run(): void {}
}
""",
        encoding="utf-8",
    )

    # 1. initialize
    init_resp = handle_mcp_request(
        tmp_path,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "groma"

    # 2. tools/list
    list_resp = handle_mcp_request(
        tmp_path,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert list_resp is not None
    tool_names = [t["name"] for t in list_resp["result"]["tools"]]
    assert "groma_find_symbol" in tool_names
    assert "groma_overview" in tool_names
    assert "groma_file_details" in tool_names
    assert "groma_impact_radius" in tool_names
    assert "groma_sync_status" in tool_names

    # 3. tools/call -> groma_find_symbol
    find_resp = handle_mcp_request(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "groma_find_symbol",
                "arguments": {"query": "UsersTableSeeder"},
            },
        },
    )
    assert find_resp is not None
    text = find_resp["result"]["content"][0]["text"]
    assert "UsersTableSeeder" in text
    assert "database/seeders/UsersTableSeeder.php" in text

    # 4. tools/call -> groma_file_details
    details_resp = handle_mcp_request(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "groma_file_details",
                "arguments": {"path": "database/seeders/UsersTableSeeder.php"},
            },
        },
    )
    assert details_resp is not None
    details_text = details_resp["result"]["content"][0]["text"]
    assert "class UsersTableSeeder" in details_text
    assert "methods: [run]" in details_text

    # 5. tools/call -> groma_sync_status
    sync_resp = handle_mcp_request(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "groma_sync_status", "arguments": {"auto_update": True}},
        },
    )
    assert sync_resp is not None
    assert "UP TO DATE" in sync_resp["result"]["content"][0]["text"]


def test_cli_find_command(tmp_path: Path) -> None:
    """Verify `groma find <query>` locates symbols from the CLI."""
    (tmp_path / "PortfoliosTableSeeder.php").write_text(
        "<?php\nclass PortfoliosTableSeeder {\n  public function seedPortfolios() {}\n}\n",
        encoding="utf-8",
    )
    runner.invoke(app, ["scan", str(tmp_path)])

    res = runner.invoke(app, ["find", "PortfoliosTableSeeder", str(tmp_path)])
    assert res.exit_code == 0
    assert "PortfoliosTableSeeder" in res.stdout

    res_missing = runner.invoke(app, ["find", "NonExistentSymbolXYZ", str(tmp_path)])
    assert res_missing.exit_code == 1

