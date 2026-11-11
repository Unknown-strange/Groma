"""Universal multi-language structural parser for PHP, JS/TS/Vue, Go, Rust, Java, SQL, etc."""

from __future__ import annotations

import re
from pathlib import Path

from groma.schema import ClassInfo, FileAnalysis, FunctionInfo, RouteInfo

# ---------------------------------------------------------------------------
# Compiled Regular Expressions for Cross-Language Extraction
# ---------------------------------------------------------------------------

# Imports
RE_ES_IMPORT = re.compile(
    r"""(?:import|export)\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""",
    re.MULTILINE,
)
RE_CJS_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
RE_PHP_USE = re.compile(r"""^\s*use\s+([A-Za-z0-9_\\]+)(?:\s+as\s+\w+)?\s*;""", re.MULTILINE)
RE_GO_RUST_JAVA_IMPORT = re.compile(
    r"""^\s*(?:import|use|package)\s+['"]?([A-Za-z0-9_./:\\]+)['"]?""",
    re.MULTILINE,
)

# Classes / Structs / Interfaces / Traits / SQL Tables
RE_CLASS_LIKE = re.compile(
    r"""^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+|final\s+|readonly\s+|pub\s+)?"""
    r"""(?:class|interface|trait|enum|struct)\s+([A-Za-z_]\w*)"""
    r"""(?:\s+extends\s+([A-Za-z0-9_\\.,\s<>]+?))?"""
    r"""(?:\s+implements\s+([A-Za-z0-9_\\.,\s<>]+?))?\s*(?:\{|:|$)""",
)
RE_GO_TYPE = re.compile(r"""^\s*type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b""")
RE_SQL_TABLE = re.compile(
    r"""^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"']?([A-Za-z0-9_.]+)[`"']?""",
    re.IGNORECASE,
)

# Functions & Methods
RE_FUNC_STANDARD = re.compile(
    r"""^\s*(?:export\s+)?(?:default\s+)?(?:public\s+|protected\s+|private\s+)?"""
    r"""(?:static\s+)?(async\s+)?(?:function|func|fn|def)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)"""
    r"""(?:\s*(?::|->)\s*([A-Za-z0-9_|?\\<>\[\]]+))?"""
)
RE_ARROW_FUNC = re.compile(
    r"""^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_]\w*)\s*=\s*(async\s+)?\(([^)]*)\)\s*(?::\s*([^=]+?))?\s*=>"""
)

# HTTP Routes (Laravel / PHP & Express / JS / TS)
RE_PHP_ROUTE = re.compile(
    r"""Route::(get|post|put|delete|patch|options|any|resource|apiResource)\s*\(\s*['"]([^'"]+)['"](?:\s*,\s*([^\n;]+))?""",
    re.IGNORECASE,
)
RE_JS_ROUTE = re.compile(
    r"""\b(?:app|router|server)\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"](?:\s*,\s*([A-Za-z0-9_.]+))?"""
)


def _split_params(raw_params: str) -> list[str]:
    """Split a raw comma-separated parameter string into clean parameter items."""
    cleaned = raw_params.strip()
    if not cleaned:
        return []
    return [p.strip() for p in cleaned.split(",") if p.strip()]


def _estimate_block_end(lines: list[str], start_idx: int) -> int:
    """Estimate the closing line (1-based) of a brace-delimited block starting at start_idx."""
    depth = 0
    opened = False
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        opens = line.count("{")
        closes = line.count("}")
        if opens > 0:
            opened = True
        depth += opens - closes
        if opened and depth <= 0:
            return idx + 1
    return min(start_idx + 1, len(lines))


def _extract_imports(content: str, language: str) -> list[str]:
    """Extract imported modules, namespaces, or relative file paths."""
    imports: set[str] = set()

    if language == "php":
        for match in RE_PHP_USE.finditer(content):
            imports.add(match.group(1).strip())
    elif language in ("javascript", "typescript", "vue", "svelte"):
        for match in RE_ES_IMPORT.finditer(content):
            imports.add(match.group(1).strip())
        for match in RE_CJS_REQUIRE.finditer(content):
            imports.add(match.group(1).strip())
    else:
        for match in RE_GO_RUST_JAVA_IMPORT.finditer(content):
            imports.add(match.group(1).strip())

    return sorted(imports)


def _extract_routes(lines: list[str], language: str) -> list[RouteInfo]:
    """Extract HTTP route declarations from PHP (Laravel) or JS/TS (Express/Fastify)."""
    routes: list[RouteInfo] = []

    for idx, line in enumerate(lines):
        line_no = idx + 1
        if language == "php":
            for m in RE_PHP_ROUTE.finditer(line):
                verb = m.group(1).upper()
                route_path = m.group(2)
                raw_handler = (m.group(3) or "closure").strip().rstrip(");")
                routes.append(
                    RouteInfo(
                        method=verb,
                        path=route_path,
                        handler=raw_handler[:80],
                        line=line_no,
                    )
                )
        elif language in ("javascript", "typescript"):
            for m in RE_JS_ROUTE.finditer(line):
                verb = m.group(1).upper()
                route_path = m.group(2)
                handler = (m.group(3) or "anonymous").strip()
                routes.append(
                    RouteInfo(
                        method=verb,
                        path=route_path,
                        handler=handler,
                        line=line_no,
                    )
                )

    return routes


def parse_universal_file(repo_root: Path, rel_posix_path: str, language: str) -> FileAnalysis:
    """Parse any supported non-Python source file into the unified FileAnalysis schema."""
    abs_path = (repo_root / rel_posix_path).resolve()
    try:
        raw_bytes = abs_path.read_bytes()
        content = raw_bytes.decode("utf-8", errors="replace")
    except OSError:
        return FileAnalysis(path=rel_posix_path, language=language)

    size = len(raw_bytes)
    lines = content.splitlines()
    lines_of_code = len(lines)

    imports = _extract_imports(content, language)
    routes = _extract_routes(lines, language)

    classes: list[ClassInfo] = []
    extracted_funcs: list[FunctionInfo] = []

    for idx, line in enumerate(lines):
        line_no = idx + 1

        # 1. Check SQL CREATE TABLE
        if language == "sql":
            sql_m = RE_SQL_TABLE.search(line)
            if sql_m:
                end_ln = _estimate_block_end(lines, idx)
                classes.append(
                    ClassInfo(
                        name=sql_m.group(1),
                        bases=["TABLE"],
                        start_line=line_no,
                        end_line=end_ln,
                    )
                )
            continue

        # 2. Check Class / Interface / Trait / Struct declarations
        cls_m = RE_CLASS_LIKE.match(line)
        if cls_m:
            cls_name = cls_m.group(1)
            bases: list[str] = []
            for grp in (cls_m.group(2), cls_m.group(3)):
                if grp:
                    bases.extend(b.strip() for b in grp.split(",") if b.strip())
            end_ln = _estimate_block_end(lines, idx)
            classes.append(
                ClassInfo(
                    name=cls_name,
                    bases=bases,
                    start_line=line_no,
                    end_line=end_ln,
                )
            )
            continue

        if language == "go":
            go_m = RE_GO_TYPE.match(line)
            if go_m:
                end_ln = _estimate_block_end(lines, idx)
                classes.append(
                    ClassInfo(
                        name=go_m.group(1),
                        start_line=line_no,
                        end_line=end_ln,
                    )
                )
                continue

        # 3. Check Standard Function / Method definitions
        fn_m = RE_FUNC_STANDARD.match(line)
        if fn_m:
            is_async = bool(fn_m.group(1))
            fn_name = fn_m.group(2)
            params = _split_params(fn_m.group(3) or "")
            ret_type = fn_m.group(4).strip() if fn_m.group(4) else None
            end_ln = _estimate_block_end(lines, idx)
            extracted_funcs.append(
                FunctionInfo(
                    name=fn_name,
                    params=params,
                    return_type=ret_type,
                    start_line=line_no,
                    end_line=end_ln,
                    is_async=is_async,
                )
            )
            continue

        # 4. Check JS/TS Arrow Functions
        if language in ("javascript", "typescript", "vue", "svelte"):
            arr_m = RE_ARROW_FUNC.match(line)
            if arr_m:
                fn_name = arr_m.group(1)
                is_async = bool(arr_m.group(2))
                params = _split_params(arr_m.group(3) or "")
                ret_type = arr_m.group(4).strip() if arr_m.group(4) else None
                end_ln = _estimate_block_end(lines, idx)
                extracted_funcs.append(
                    FunctionInfo(
                        name=fn_name,
                        params=params,
                        return_type=ret_type,
                        start_line=line_no,
                        end_line=end_ln,
                        is_async=is_async,
                    )
                )

    # Associate methods nested inside class line spans with their enclosing ClassInfo
    top_level_functions: list[FunctionInfo] = []
    for fn in extracted_funcs:
        attached = False
        for cls in classes:
            if cls.start_line < fn.start_line <= cls.end_line:
                cls.methods.append(fn)
                attached = True
                break
        if not attached:
            top_level_functions.append(fn)

    return FileAnalysis(
        path=rel_posix_path,
        language=language,
        size=size,
        lines_of_code=lines_of_code,
        imports=imports,
        classes=classes,
        functions=top_level_functions,
        routes=routes,
    )

