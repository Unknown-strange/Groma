"""Repository scanner, .gitignore filter, dependency-file filter, and framework detector."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

# Hard-coded directories, caches, dependency folders, and dependency files to ignore
DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    # Version control & Groma state
    ".git/",
    ".hg/",
    ".svn/",
    ".groma/",
    ".agents/",
    # Dependency & Virtual Environment directories across ecosystems
    ".venv/",
    "venv/",
    "env/",
    ".env/",
    "virtualenv/",
    "__pypackages__/",
    "site-packages/",
    "node_modules/",
    "bower_components/",
    "jspm_packages/",
    "vendor/",
    "packages/",
    "target/",
    "Pods/",
    ".gradle/",
    ".m2/",
    # Build, cache, and coverage directories
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".tox/",
    ".nox/",
    ".hypothesis/",
    "dist/",
    "build/",
    "out/",
    ".next/",
    ".nuxt/",
    ".svelte-kit/",
    ".turbo/",
    "coverage/",
    "htmlcov/",
    "*.egg-info/",
    # Environment & secret files
    ".env",
    ".env.*",
    # Dependency manifests & lockfiles across different project types
    "requirements.txt",
    "requirements-*.txt",
    "requirements_*.txt",
    "requirements/*.txt",
    "constraints.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
    "conda.yaml",
    "environment.yml",
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
    "deno.json",
    "deno.lock",
    "composer.json",
    "composer.lock",
    "Gemfile",
    "Gemfile.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.lockfile",
    "Podfile",
    "Podfile.lock",
    "pubspec.yaml",
    "pubspec.lock",
    "mix.exs",
    "mix.lock",
    # Compiled / binary artifacts
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.class",
)

# Explicit set of dependency filenames for fast exact lookup
DEPENDENCY_FILENAMES: frozenset[str] = frozenset(
    {
        "requirements.txt",
        "constraints.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "pdm.lock",
        "uv.lock",
        "conda.yaml",
        "environment.yml",
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "bun.lock",
        "deno.json",
        "deno.lock",
        "composer.json",
        "composer.lock",
        "gemfile",
        "gemfile.lock",
        "go.mod",
        "go.sum",
        "cargo.toml",
        "cargo.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "gradle.lockfile",
        "podfile",
        "podfile.lock",
        "pubspec.yaml",
        "pubspec.lock",
        "mix.exs",
        "mix.lock",
    }
)

# Supported source code extensions mapped to their canonical language identifier
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

# Known framework signatures (dependency token -> canonical display name)
PYTHON_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "starlette": "Starlette",
    "litestar": "Litestar",
    "tornado": "Tornado",
    "sanic": "Sanic",
    "aiohttp": "aiohttp",
    "typer": "Typer",
    "click": "Click",
    "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy",
    "celery": "Celery",
    "pytest": "Pytest",
}

JS_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "next": "Next.js",
    "react": "React",
    "vue": "Vue.js",
    "nuxt": "Nuxt",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "express": "Express",
    "fastify": "Fastify",
    "@nestjs/core": "NestJS",
    "hono": "Hono",
    "koa": "Koa",
}

PHP_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "laravel/framework": "Laravel",
    "symfony/symfony": "Symfony",
    "symfony/framework-bundle": "Symfony",
    "slim/slim": "Slim",
}


@dataclass
class ScanResult:
    """Output of scanning a target repository."""

    files: list[tuple[str, str]] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)


def is_dependency_file(rel_posix_path: str) -> bool:
    """Return True if the file is a dependency manifest or lockfile."""
    name_lower = Path(rel_posix_path).name.lower()
    if name_lower in DEPENDENCY_FILENAMES:
        return True
    if name_lower.startswith("requirements") and name_lower.endswith((".txt", ".in")):
        return True
    return name_lower.endswith((".lock", "-lock.json"))


def load_ignore_spec(repo_root: Path) -> pathspec.PathSpec:
    """Combine default ignore patterns with all `.gitignore` files in the repository."""
    patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)

    root_gitignore = repo_root / ".gitignore"
    if root_gitignore.is_file():
        try:
            lines = root_gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
            patterns.extend(lines)
        except OSError:
            pass

    return pathspec.PathSpec.from_lines("gitignore", patterns)


def _load_nested_gitignore_patterns(
    repo_root: Path, dir_path: Path
) -> list[str]:
    """Load patterns from a nested `.gitignore` scoped to its relative directory."""
    nested_gitignore = dir_path / ".gitignore"
    if dir_path == repo_root or not nested_gitignore.is_file():
        return []

    rel_dir = dir_path.relative_to(repo_root).as_posix()
    scoped_patterns: list[str] = []
    try:
        lines = nested_gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                negated = line[1:].lstrip("/")
                scoped_patterns.append(f"!{rel_dir}/{negated}")
            else:
                clean = line.lstrip("/")
                scoped_patterns.append(f"{rel_dir}/{clean}")
                scoped_patterns.append(f"{rel_dir}/**/{clean}")
    except OSError:
        pass
    return scoped_patterns


def detect_frameworks(repo_root: Path) -> list[str]:
    """Passively inspect project manifests to detect frameworks without tracking those files."""
    detected: set[str] = set()

    # 1. Inspect pyproject.toml
    pyproject_path = repo_root / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            content = pyproject_path.read_text(encoding="utf-8", errors="ignore").lower()
            for token, display_name in PYTHON_FRAMEWORK_SIGNATURES.items():
                if re.search(rf"\b{re.escape(token)}\b", content):
                    detected.add(display_name)
        except OSError:
            pass

    # 2. Inspect requirements*.txt
    for req_file in repo_root.glob("requirements*.txt"):
        if req_file.is_file():
            try:
                content = req_file.read_text(encoding="utf-8", errors="ignore").lower()
                for token, display_name in PYTHON_FRAMEWORK_SIGNATURES.items():
                    if re.search(rf"^\s*{re.escape(token)}\b", content, flags=re.MULTILINE):
                        detected.add(display_name)
            except OSError:
                pass

    # 3. Inspect package.json
    package_json_path = repo_root / "package.json"
    if package_json_path.is_file():
        try:
            data = json.loads(package_json_path.read_text(encoding="utf-8", errors="ignore"))
            deps: dict[str, str] = {}
            if isinstance(data, dict):
                for section in ("dependencies", "devDependencies", "peerDependencies"):
                    sec_data = data.get(section)
                    if isinstance(sec_data, dict):
                        deps.update(sec_data)
            for pkg_name, display_name in JS_FRAMEWORK_SIGNATURES.items():
                if pkg_name in deps:
                    detected.add(display_name)
        except (OSError, json.JSONDecodeError):
            pass

    # 4. Inspect composer.json
    composer_json_path = repo_root / "composer.json"
    if composer_json_path.is_file():
        try:
            data = json.loads(composer_json_path.read_text(encoding="utf-8", errors="ignore"))
            deps = {}
            if isinstance(data, dict):
                for section in ("require", "require-dev"):
                    sec_data = data.get(section)
                    if isinstance(sec_data, dict):
                        deps.update(sec_data)
            for pkg_name, display_name in PHP_FRAMEWORK_SIGNATURES.items():
                if pkg_name in deps:
                    detected.add(display_name)
        except (OSError, json.JSONDecodeError):
            pass

    return sorted(detected)


def scan_repository(repo_root: Path) -> ScanResult:
    """Walk the repository, ignoring all .gitignore matches and dependency files.

    Returns only supported source code files as sorted (rel_posix_path, language) tuples,
    plus a sorted list of detected frameworks.
    """
    repo_root = repo_root.resolve()
    base_patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)

    root_gitignore = repo_root / ".gitignore"
    if root_gitignore.is_file():
        try:
            base_patterns.extend(
                root_gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
            )
        except OSError:
            pass

    ignore_spec = pathspec.PathSpec.from_lines("gitignore", base_patterns)
    tracked_files: list[tuple[str, str]] = []

    for current_root, dirs, files in os.walk(repo_root, topdown=True):
        current_dir = Path(current_root)

        # Incorporate nested .gitignore if present in this directory
        nested_patterns = _load_nested_gitignore_patterns(repo_root, current_dir)
        if nested_patterns:
            base_patterns.extend(nested_patterns)
            ignore_spec = pathspec.PathSpec.from_lines("gitignore", base_patterns)

        # Prune ignored directories in-place (sorted for deterministic traversal)
        kept_dirs: list[str] = []
        for d in sorted(dirs):
            dir_rel_posix = (current_dir / d).relative_to(repo_root).as_posix()
            if ignore_spec.match_file(dir_rel_posix) or ignore_spec.match_file(f"{dir_rel_posix}/"):
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        # Filter files in the current directory
        for filename in sorted(files):
            file_path = current_dir / filename
            rel_posix = file_path.relative_to(repo_root).as_posix()

            # 1. Skip if matched by .gitignore or default ignore patterns
            if ignore_spec.match_file(rel_posix):
                continue

            # 2. Skip if it is a dependency manifest or lockfile
            if is_dependency_file(rel_posix):
                continue

            # 3. Only track supported source code extensions
            ext = file_path.suffix.lower()
            language = EXTENSION_LANGUAGE_MAP.get(ext)
            if language is None:
                continue

            tracked_files.append((rel_posix, language))

    tracked_files.sort(key=lambda item: item[0])
    frameworks = detect_frameworks(repo_root)
    return ScanResult(files=tracked_files, frameworks=frameworks)
