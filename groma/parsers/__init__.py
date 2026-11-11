"""Language parsers dispatcher, FileIndex cache, and file-index.json persistence."""

from __future__ import annotations

from pathlib import Path

from groma.parsers.python_ast import parse_python_file
from groma.parsers.universal import parse_universal_file
from groma.schema import FileAnalysis, FileIndex

FILE_INDEX_REL_PATH = Path(".groma") / "file-index.json"


def parse_source_file(repo_root: Path, rel_posix_path: str, language: str) -> FileAnalysis:
    """Dispatch a source file to the appropriate parser based on its language."""
    if language == "python":
        return parse_python_file(repo_root, rel_posix_path)
    return parse_universal_file(repo_root, rel_posix_path, language)


def build_file_index(
    repo_root: Path,
    scanned_files: list[tuple[str, str]],
    previous_index: FileIndex | None = None,
    changed_files: set[str] | None = None,
    project_name: str | None = None,
) -> FileIndex:
    """Build or update a FileIndex across all tracked files.

    If `previous_index` is provided alongside `changed_files`, unchanged files
    are reused from the cache without re-parsing.
    """
    repo_root = repo_root.resolve()
    resolved_name = project_name or repo_root.name
    prev_entries = previous_index.files if previous_index else {}

    files_map: dict[str, FileAnalysis] = {}

    for rel_posix, language in scanned_files:
        # Re-parse if:
        # 1. We don't have a changed_files filter (full scan) and it's not in cache
        # 2. It's explicitly in changed_files
        # 3. It's missing from previous_index
        must_parse = (
            changed_files is None
            or rel_posix in changed_files
            or rel_posix not in prev_entries
        )

        if not must_parse and rel_posix in prev_entries:
            files_map[rel_posix] = prev_entries[rel_posix]
        else:
            files_map[rel_posix] = parse_source_file(repo_root, rel_posix, language)

    return FileIndex(
        project_name=resolved_name,
        files=files_map,
    )


def save_file_index(repo_root: Path, file_index: FileIndex) -> Path:
    """Save `.groma/file-index.json` to disk and return the path."""
    dest = repo_root.resolve() / FILE_INDEX_REL_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(file_index.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return dest


def load_file_index(repo_root: Path) -> FileIndex | None:
    """Load `.groma/file-index.json` from disk, or return None if missing/invalid."""
    src = repo_root.resolve() / FILE_INDEX_REL_PATH
    if not src.is_file():
        return None
    try:
        raw_json = src.read_text(encoding="utf-8")
        return FileIndex.model_validate_json(raw_json)
    except (OSError, ValueError):
        return None
