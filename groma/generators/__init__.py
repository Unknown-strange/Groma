"""Markdown, SKILL.md, and rule document generators for Groma."""

from __future__ import annotations

from pathlib import Path

from groma.generators.markdown import render_markdown_docs
from groma.generators.rules import render_agent_rules
from groma.generators.skill import render_skill_doc
from groma.graph import DependencyGraph
from groma.schema import FileIndex, Manifest


def generate_all_docs(
    repo_root: Path,
    manifest: Manifest,
    file_index: FileIndex,
    graph: DependencyGraph,
    project_name: str | None = None,
) -> list[Path]:
    """Generate all .groma/*.md documents, SKILL.md, and agent sync rules."""
    md_paths = render_markdown_docs(repo_root, manifest, file_index, graph)
    skill_path = render_skill_doc(repo_root, manifest, project_name=project_name)
    rule_paths = render_agent_rules(repo_root)
    return list(md_paths.values()) + [skill_path] + rule_paths


__all__ = [
    "generate_all_docs",
    "render_agent_rules",
    "render_markdown_docs",
    "render_skill_doc",
]
