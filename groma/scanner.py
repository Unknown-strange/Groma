"""Repository scanner, .gitignore filter, and dependency-file filter for all languages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

# Hard-coded directories, caches, dependency folders, and dependency files to ignore
DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    # Version control & Groma / IDE state
    ".git/",
    ".hg/",
    ".svn/",
    ".groma/",
    ".agents/",
    ".gemini/",
    ".cursor/",
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
    # Compiled / binary / minified artifacts
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.class",
    "*.min.js",
    "*.min.css",
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

# Universal source code, backend, frontend, database, and config extensions
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    # Python
    ".py": "python",
    # JavaScript & TypeScript & Frontend Frameworks
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
    ".svelte": "svelte",
    # PHP (Laravel, Symfony, WordPress, etc.)
    ".php": "php",
    # Go, Rust, C/C++
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    # JVM & .NET
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    # Ruby, Swift, Dart, Elixir
    ".rb": "ruby",
    ".swift": "swift",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    # Database, API Schemas, & Infrastructure Configs
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
}


@dataclass
class ScanResult:
    """Output of scanning a target repository."""

    files: list[tuple[str, str]] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)


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


def scan_repository(repo_root: Path) -> ScanResult:
    """Walk the repository, ignoring all .gitignore matches and dependency files.

    Returns supported source files as sorted (rel_posix_path, language) tuples,
    plus a sorted list of unique languages present in the codebase.
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
    languages_found: set[str] = set()

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

            # 3. Only track supported source/config extensions
            ext = file_path.suffix.lower()
            language = EXTENSION_LANGUAGE_MAP.get(ext)
            if language is None:
                continue

            tracked_files.append((rel_posix, language))
            languages_found.add(language)

    tracked_files.sort(key=lambda item: item[0])
    return ScanResult(files=tracked_files, languages=sorted(languages_found))
