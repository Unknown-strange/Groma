"""Unified data contract (Pydantic v2 models) for Groma.

All language parsers, manifest engines, dependency graphs, and markdown generators
communicate exclusively through these models.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Manifest & Diff Models (.groma/manifest.json)
# ---------------------------------------------------------------------------


class FileHashEntry(BaseModel):
    """Per-file snapshot metadata stored in .groma/manifest.json."""

    hash: str = Field(..., description="SHA-256 hex digest of the file contents")
    size: int = Field(..., ge=0, description="File size in bytes")
    mtime: float = Field(..., description="Last modified timestamp (POSIX seconds)")
    language: str = Field(..., description="Detected language or file category (e.g. 'python')")


class Manifest(BaseModel):
    """Complete repository hash baseline stored at .groma/manifest.json."""

    project_name: str = Field(..., description="Name of the target project/repository")
    generated_at: str = Field(
        default_factory=utc_now_iso,
        description="ISO-8601 UTC timestamp when the manifest was generated",
    )
    fingerprint: str = Field(
        ..., description="Summary SHA-256 hash computed over all sorted path:hash pairs"
    )
    frameworks: list[str] = Field(
        default_factory=list,
        description="Detected frameworks (e.g. FastAPI, Django, Next.js, React)",
    )
    files: dict[str, FileHashEntry] = Field(
        default_factory=dict,
        description="Mapping of relative POSIX file path to FileHashEntry",
    )


class DiffResult(BaseModel):
    """Comparison result between disk state and .groma/manifest.json."""

    added: list[str] = Field(default_factory=list, description="New files on disk")
    modified: list[str] = Field(
        default_factory=list, description="Existing files with a changed SHA-256 hash"
    )
    deleted: list[str] = Field(
        default_factory=list, description="Files in manifest that no longer exist on disk"
    )
    renamed: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of old_path -> new_path for files moved with identical SHA-256 hash",
    )
    unchanged: list[str] = Field(
        default_factory=list, description="Files whose SHA-256 hash matches the manifest"
    )

    @property
    def is_clean(self) -> bool:
        """Return True if no files were added, modified, deleted, or renamed."""
        return not (self.added or self.modified or self.deleted or self.renamed)

    @property
    def changed_files(self) -> list[str]:
        """Return all paths that require re-parsing or graph updates."""
        return sorted(set(self.added + self.modified + list(self.renamed.values())))


# ---------------------------------------------------------------------------
# AST & Code Analysis Models (.groma/file-index.json)
# ---------------------------------------------------------------------------


class FunctionInfo(BaseModel):
    """Extracted metadata for a standalone function or class method."""

    name: str = Field(..., description="Function or method name")
    params: list[str] = Field(
        default_factory=list,
        description="Formatted parameter strings (e.g. ['user_id: int', 'active: bool = True'])",
    )
    return_type: str | None = Field(
        default=None, description="Return type annotation if present"
    )
    decorators: list[str] = Field(
        default_factory=list, description="Decorator expressions applied to the function"
    )
    docstring: str | None = Field(
        default=None, description="First line or summary of the function docstring"
    )
    start_line: int = Field(..., ge=1, description="1-based starting line number")
    end_line: int = Field(..., ge=1, description="1-based ending line number")
    is_async: bool = Field(default=False, description="True if defined with async def / async")
    calls: list[str] = Field(
        default_factory=list, description="Names of functions/methods called within the body"
    )


class ClassInfo(BaseModel):
    """Extracted metadata for a class definition."""

    name: str = Field(..., description="Class name")
    bases: list[str] = Field(default_factory=list, description="Base classes / interfaces")
    decorators: list[str] = Field(default_factory=list, description="Class decorators")
    docstring: str | None = Field(
        default=None, description="First line or summary of the class docstring"
    )
    start_line: int = Field(..., ge=1, description="1-based starting line number")
    end_line: int = Field(..., ge=1, description="1-based ending line number")
    methods: list[FunctionInfo] = Field(
        default_factory=list, description="Methods defined inside the class"
    )


class RouteInfo(BaseModel):
    """Extracted HTTP route / endpoint definition (e.g. FastAPI, Flask, Express)."""

    method: str = Field(..., description="HTTP verb (GET, POST, PUT, DELETE, PATCH, etc.)")
    path: str = Field(..., description="URL route path (e.g. '/api/v1/users')")
    handler: str = Field(..., description="Name of the handler function or method")
    line: int = Field(..., ge=1, description="1-based line number of the route declaration")


class FileAnalysis(BaseModel):
    """Unified, language-agnostic structural analysis of a single source file."""

    path: str = Field(..., description="Relative POSIX path from repository root")
    language: str = Field(..., description="Source language (e.g. 'python', 'typescript')")
    size: int = Field(default=0, ge=0, description="File size in bytes")
    lines_of_code: int = Field(default=0, ge=0, description="Total line count of the file")
    module_docstring: str | None = Field(
        default=None, description="Top-level module docstring if present"
    )
    imports: list[str] = Field(
        default_factory=list,
        description="Raw imported module or symbol references extracted from the file",
    )
    classes: list[ClassInfo] = Field(
        default_factory=list, description="Classes defined in the file"
    )
    functions: list[FunctionInfo] = Field(
        default_factory=list, description="Top-level functions defined in the file"
    )
    routes: list[RouteInfo] = Field(
        default_factory=list, description="HTTP API routes declared in the file"
    )


class FileIndex(BaseModel):
    """Cached AST symbol index stored at .groma/file-index.json."""

    project_name: str = Field(..., description="Name of the target project/repository")
    updated_at: str = Field(
        default_factory=utc_now_iso,
        description="ISO-8601 UTC timestamp when the index was last updated",
    )
    files: dict[str, FileAnalysis] = Field(
        default_factory=dict,
        description="Mapping of relative POSIX file path to its parsed FileAnalysis",
    )
