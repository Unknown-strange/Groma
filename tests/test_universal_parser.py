"""Unit tests for Groma's universal multi-language parser and cross-language dependency graph."""

from pathlib import Path

from groma.graph import DependencyGraph
from groma.parsers import build_file_index
from groma.scanner import scan_repository


def test_php_laravel_seeder_model_route_and_graph(tmp_path: Path) -> None:
    """Verify PHP classes, methods, Laravel routes, and PSR-4 namespace imports are indexed."""
    model_dir = tmp_path / "app" / "Models"
    model_dir.mkdir(parents=True)
    (model_dir / "User.php").write_text(
        """<?php
namespace App\\Models;

class User extends Authenticatable
{
    public function portfolios(): HasMany
    {
        return $this->hasMany(Portfolio::class);
    }
}
""",
        encoding="utf-8",
    )

    seeder_dir = tmp_path / "database" / "seeders"
    seeder_dir.mkdir(parents=True)
    (seeder_dir / "UsersTableSeeder.php").write_text(
        """<?php
namespace Database\\Seeders;

use App\\Models\\User;
use Illuminate\\Database\\Seeder;

class UsersTableSeeder extends Seeder
{
    public function run(): void
    {
        User::create(['email' => 'admin@example.com']);
    }
}
""",
        encoding="utf-8",
    )

    routes_dir = tmp_path / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "api.php").write_text(
        """<?php
use App\\Models\\User;

Route::get('/api/v1/users', [UserController::class, 'index']);
Route::post('/api/v1/portfolios', 'PortfolioController@store');
""",
        encoding="utf-8",
    )

    scan = scan_repository(tmp_path)
    assert scan.languages == ["php"]

    file_index = build_file_index(tmp_path, scan.files)

    # Verify UsersTableSeeder.php symbols
    seeder_analysis = file_index.files["database/seeders/UsersTableSeeder.php"]
    assert len(seeder_analysis.classes) == 1
    assert seeder_analysis.classes[0].name == "UsersTableSeeder"
    assert seeder_analysis.classes[0].bases == ["Seeder"]
    assert len(seeder_analysis.classes[0].methods) == 1
    assert seeder_analysis.classes[0].methods[0].name == "run"
    assert "App\\Models\\User" in seeder_analysis.imports

    # Verify routes/api.php routes
    routes_analysis = file_index.files["routes/api.php"]
    assert len(routes_analysis.routes) == 2
    assert routes_analysis.routes[0].method == "GET"
    assert routes_analysis.routes[0].path == "/api/v1/users"
    assert routes_analysis.routes[1].method == "POST"
    assert routes_analysis.routes[1].path == "/api/v1/portfolios"

    # Verify PSR-4 Dependency Graph: UsersTableSeeder.php & routes/api.php -> app/Models/User.php
    graph = DependencyGraph(file_index)
    assert graph.imports_of("database/seeders/UsersTableSeeder.php") == ["app/Models/User.php"]
    assert graph.imported_by("app/Models/User.php") == [
        "database/seeders/UsersTableSeeder.php",
        "routes/api.php",
    ]
    assert graph.impact_radius(["app/Models/User.php"]) == [
        "database/seeders/UsersTableSeeder.php",
        "routes/api.php",
    ]


def test_typescript_vue_and_sql_indexing(tmp_path: Path) -> None:
    """Verify TypeScript arrow functions, Vue imports, and SQL CREATE TABLE extraction."""
    src_dir = tmp_path / "frontend" / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "api.ts").write_text(
        """export const fetchPortfolios = async (userId: string): Promise<any> => {
    return [];
};
""",
        encoding="utf-8",
    )
    (src_dir / "Dashboard.vue").write_text(
        """<script setup lang="ts">
import { fetchPortfolios } from './api';
function refreshView() {
    fetchPortfolios('1');
}
</script>
""",
        encoding="utf-8",
    )
    (tmp_path / "migration.sql").write_text(
        """CREATE TABLE IF NOT EXISTS portfolios (
    id INT PRIMARY KEY
);
""",
        encoding="utf-8",
    )

    scan = scan_repository(tmp_path)
    file_index = build_file_index(tmp_path, scan.files)
    graph = DependencyGraph(file_index)

    api_file = file_index.files["frontend/src/api.ts"]
    assert len(api_file.functions) == 1
    assert api_file.functions[0].name == "fetchPortfolios"
    assert api_file.functions[0].is_async is True

    sql_file = file_index.files["migration.sql"]
    assert len(sql_file.classes) == 1
    assert sql_file.classes[0].name == "portfolios"

    assert graph.imports_of("frontend/src/Dashboard.vue") == ["frontend/src/api.ts"]

