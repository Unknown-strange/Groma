"""SHA-256 snapshot, fast size/mtime cache check, project fingerprinting, and diff engine."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from groma.schema import DiffResult, FileHashEntry, Manifest

CHUNK_SIZE = 65536  # 64 KB streaming chunks
MANIFEST_REL_PATH = Path(".groma") / "manifest.json"
MTIME_TOLERANCE = 1e-6


def compute_file_sha256(file_path: Path) -> str:
    """Stream a file in 64 KB chunks and return its SHA-256 hex digest."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_project_fingerprint(files: dict[str, FileHashEntry]) -> str:
    """Compute a single deterministic summary SHA-256 over all sorted path:hash pairs."""
    hasher = hashlib.sha256()
    for rel_path in sorted(files.keys()):
        entry = files[rel_path]
        hasher.update(f"{rel_path}:{entry.hash}\n".encode())
    return hasher.hexdigest()


def build_manifest(
    repo_root: Path,
    scanned_files: list[tuple[str, str]],
    languages: list[str] | None = None,
    previous_manifest: Manifest | None = None,
    project_name: str | None = None,
) -> Manifest:
    """Build a fresh Manifest for the scanned files, reusing cached hashes when unchanged.

    If `previous_manifest` is supplied and a file's `size` and `mtime` match its cached
    entry, the existing SHA-256 hash is reused without reading the file's bytes from disk.
    """
    repo_root = repo_root.resolve()
    resolved_project_name = project_name or repo_root.name
    prev_files = previous_manifest.files if previous_manifest else {}

    file_entries: dict[str, FileHashEntry] = {}
    detected_langs: set[str] = set(languages or [])

    for rel_posix, language in sorted(scanned_files, key=lambda item: item[0]):
        abs_path = repo_root / rel_posix
        try:
            stat = abs_path.stat()
        except OSError:
            continue

        size = stat.st_size
        mtime = stat.st_mtime
        detected_langs.add(language)

        prev_entry = prev_files.get(rel_posix)
        if (
            prev_entry is not None
            and prev_entry.size == size
            and abs(prev_entry.mtime - mtime) < MTIME_TOLERANCE
        ):
            file_hash = prev_entry.hash
        else:
            file_hash = compute_file_sha256(abs_path)

        file_entries[rel_posix] = FileHashEntry(
            hash=file_hash,
            size=size,
            mtime=mtime,
            language=language,
        )

    fingerprint = compute_project_fingerprint(file_entries)
    return Manifest(
        project_name=resolved_project_name,
        fingerprint=fingerprint,
        languages=sorted(detected_langs),
        files=file_entries,
    )


def diff_manifests(old_manifest: Manifest, new_manifest: Manifest) -> DiffResult:
    """Compare an existing baseline Manifest against a current Manifest.

    Classifies files into:
    - unchanged: Same path, identical SHA-256 hash
    - modified: Same path, different SHA-256 hash
    - renamed: Path in deleted + path in added sharing the exact same SHA-256 hash
    - added: Path only in new_manifest (not matched by rename)
    - deleted: Path only in old_manifest (not matched by rename)
    """
    old_files = old_manifest.files
    new_files = new_manifest.files

    old_paths = set(old_files.keys())
    new_paths = set(new_files.keys())

    common_paths = old_paths & new_paths
    raw_added = sorted(new_paths - old_paths)
    raw_deleted = sorted(old_paths - new_paths)

    unchanged: list[str] = []
    modified: list[str] = []

    for path in sorted(common_paths):
        if old_files[path].hash == new_files[path].hash:
            unchanged.append(path)
        else:
            modified.append(path)

    # Detect renames by matching SHA-256 digests between raw_deleted and raw_added
    deleted_by_hash: dict[str, list[str]] = defaultdict(list)
    for del_path in raw_deleted:
        deleted_by_hash[old_files[del_path].hash].append(del_path)

    renamed: dict[str, str] = {}
    matched_deleted: set[str] = set()
    final_added: list[str] = []

    for add_path in raw_added:
        add_hash = new_files[add_path].hash
        candidates = deleted_by_hash.get(add_hash, [])
        if candidates:
            old_path = candidates.pop(0)
            renamed[old_path] = add_path
            matched_deleted.add(old_path)
        else:
            final_added.append(add_path)

    final_deleted = [p for p in raw_deleted if p not in matched_deleted]

    return DiffResult(
        added=final_added,
        modified=modified,
        deleted=final_deleted,
        renamed=renamed,
        unchanged=unchanged,
    )


def save_manifest(repo_root: Path, manifest: Manifest) -> Path:
    """Write `.groma/manifest.json` to disk and return the saved file path."""
    manifest_path = repo_root.resolve() / MANIFEST_REL_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest_path


def load_manifest(repo_root: Path) -> Manifest | None:
    """Load `.groma/manifest.json` from disk, or return None if it does not exist."""
    manifest_path = repo_root.resolve() / MANIFEST_REL_PATH
    if not manifest_path.is_file():
        return None
    raw_json = manifest_path.read_text(encoding="utf-8")
    return Manifest.model_validate_json(raw_json)
