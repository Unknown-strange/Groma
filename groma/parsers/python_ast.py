"""Built-in Python AST parser extracting classes, functions, calls, imports, and HTTP routes."""

from __future__ import annotations

import ast
from pathlib import Path

from groma.schema import ClassInfo, FileAnalysis, FunctionInfo, RouteInfo

HTTP_VERBS: frozenset[str] = frozenset(
    {"get", "post", "put", "delete", "patch", "options", "head"}
)


def _safe_unparse(node: ast.AST | None, default: str = "") -> str:
    """Safely convert an AST node to source text, returning default on failure."""
    if node is None:
        return default
    try:
        return ast.unparse(node)
    except (ValueError, TypeError, AttributeError, RecursionError):
        return default


def _format_arg(arg: ast.arg, default: ast.AST | None = None) -> str:
    """Format an ast.arg with optional type annotation and default value."""
    text = arg.arg
    if arg.annotation is not None:
        ann = _safe_unparse(arg.annotation)
        if ann:
            text = f"{text}: {ann}"
    if default is not None:
        def_val = _safe_unparse(default)
        if def_val:
            text = f"{text} = {def_val}"
    return text


def _extract_parameters(args_node: ast.arguments) -> list[str]:
    """Format all parameter declarations into human-readable strings."""
    params: list[str] = []

    # Positional-only arguments
    posonly = list(args_node.posonlyargs)
    pos_defaults = [None] * (len(posonly) + len(args_node.args) - len(args_node.defaults)) + list(
        args_node.defaults
    )
    for arg, default in zip(posonly, pos_defaults[: len(posonly)]):
        params.append(_format_arg(arg, default))
    if posonly:
        params.append("/")

    # Regular positional/keyword arguments
    for arg, default in zip(args_node.args, pos_defaults[len(posonly) :]):
        params.append(_format_arg(arg, default))

    # Vararg (*args)
    if args_node.vararg is not None:
        var_text = f"*{args_node.vararg.arg}"
        if args_node.vararg.annotation is not None:
            ann = _safe_unparse(args_node.vararg.annotation)
            if ann:
                var_text = f"{var_text}: {ann}"
        params.append(var_text)
    elif args_node.kwonlyargs:
        params.append("*")

    # Keyword-only arguments
    for arg, default in zip(args_node.kwonlyargs, args_node.kw_defaults):
        params.append(_format_arg(arg, default))

    # Kwarg (**kwargs)
    if args_node.kwarg is not None:
        kw_text = f"**{args_node.kwarg.arg}"
        if args_node.kwarg.annotation is not None:
            ann = _safe_unparse(args_node.kwarg.annotation)
            if ann:
                kw_text = f"{kw_text}: {ann}"
        params.append(kw_text)

    return params


def _clean_docstring(doc: str | None) -> str | None:
    """Extract the first non-empty line of a docstring as a summary."""
    if not doc:
        return None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _extract_call_names(node: ast.AST) -> list[str]:
    """Recursively collect unique function/method call names within an AST node."""
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            call_repr = _safe_unparse(child.func).strip()
            if call_repr:
                calls.add(call_repr)
    return sorted(calls)


def _extract_decorator_str(dec_node: ast.AST) -> str:
    """Unparse a decorator node into an '@expr' string."""
    rep = _safe_unparse(dec_node)
    return f"@{rep}" if rep else "@<unknown>"


def _extract_routes_from_decorators(
    decorators: list[ast.AST], handler_name: str, line_no: int
) -> list[RouteInfo]:
    """Inspect decorators for HTTP route signatures (FastAPI, Flask, Starlette, Express)."""
    routes: list[RouteInfo] = []

    for dec in decorators:
        # Check call decorators: @app.get("/items"), @router.post("/login"), @app.route("/path")
        if not isinstance(dec, ast.Call):
            continue

        func = dec.func
        # @obj.verb(...) e.g. @app.get("/items") or @router.post("/login")
        if isinstance(func, ast.Attribute) and func.attr.lower() in HTTP_VERBS:
            verb = func.attr.upper()
            path_val: str | None = None
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                path_val = dec.args[0].value
            elif dec.keywords:
                for kw in dec.keywords:
                    if kw.arg in ("path", "url") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        path_val = kw.value.value
                        break
            if path_val is not None:
                routes.append(
                    RouteInfo(
                        method=verb,
                        path=path_val,
                        handler=handler_name,
                        line=line_no,
                    )
                )

        # @app.route("/path", methods=["GET", "POST"]) or @router.api_route("/path", methods=[...])
        elif isinstance(func, ast.Attribute) and func.attr.lower() in ("route", "api_route"):
            path_val: str | None = None
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                path_val = dec.args[0].value

            methods: list[str] = []
            for kw in dec.keywords:
                if kw.arg in ("path", "rule") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    path_val = kw.value.value
                elif kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            methods.append(elt.value.upper())

            if not methods:
                methods = ["GET"]  # Default HTTP verb in Flask/Flask-style routers

            if path_val is not None:
                for m in methods:
                    routes.append(
                        RouteInfo(
                            method=m,
                            path=path_val,
                            handler=handler_name,
                            line=line_no,
                        )
                    )

    return routes


def _parse_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[FunctionInfo, list[RouteInfo]]:
    """Convert an AST function definition into FunctionInfo and RouteInfo entries."""
    params = _extract_parameters(node.args)
    return_type: str | None = None
    if node.returns is not None:
        ret_str = _safe_unparse(node.returns)
        if ret_str:
            return_type = ret_str

    decorators = [_extract_decorator_str(d) for d in node.decorator_list]
    docstring = _clean_docstring(ast.get_docstring(node))
    calls = _extract_call_names(node)

    func_info = FunctionInfo(
        name=node.name,
        params=params,
        return_type=return_type,
        decorators=decorators,
        docstring=docstring,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        calls=calls,
    )

    routes = _extract_routes_from_decorators(node.decorator_list, node.name, node.lineno)
    return func_info, routes


def _parse_class(node: ast.ClassDef) -> tuple[ClassInfo, list[RouteInfo]]:
    """Convert an AST class definition into ClassInfo and any nested RouteInfo entries."""
    bases: list[str] = []
    for b in node.bases:
        b_str = _safe_unparse(b)
        if b_str:
            bases.append(b_str)

    decorators = [_extract_decorator_str(d) for d in node.decorator_list]
    docstring = _clean_docstring(ast.get_docstring(node))

    methods: list[FunctionInfo] = []
    class_routes: list[RouteInfo] = []

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            m_info, m_routes = _parse_function(item)
            methods.append(m_info)
            class_routes.extend(m_routes)

    cls_info = ClassInfo(
        name=node.name,
        bases=bases,
        decorators=decorators,
        docstring=docstring,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        methods=methods,
    )

    return cls_info, class_routes


def _resolve_relative_import(base_rel_path: str, level: int, module: str | None) -> str:
    """Resolve Python relative import (e.g. level=1, module='schema') to a dotted module path."""
    parts = list(Path(base_rel_path).parent.parts)
    # Go up (level - 1) additional directories from current file's package
    if level > 1:
        parts = parts[: -(level - 1)]
    prefix = ".".join(parts)
    if prefix and module:
        return f"{prefix}.{module}"
    if prefix:
        return prefix
    return module or ""


def parse_python_file(repo_root: Path, rel_posix_path: str) -> FileAnalysis:
    """Parse a Python source file using ast into the unified FileAnalysis model.

    Gracefully handles syntax errors during active editing by returning a baseline model.
    """
    abs_path = (repo_root / rel_posix_path).resolve()
    try:
        raw_bytes = abs_path.read_bytes()
        content = raw_bytes.decode("utf-8", errors="replace")
    except OSError:
        return FileAnalysis(path=rel_posix_path, language="python")

    size = len(raw_bytes)
    lines_of_code = len(content.splitlines())

    try:
        tree = ast.parse(content, filename=rel_posix_path)
    except SyntaxError:
        # File may be mid-edit or invalid syntax: return basic stats without crashing
        return FileAnalysis(
            path=rel_posix_path,
            language="python",
            size=size,
            lines_of_code=lines_of_code,
        )

    module_docstring = _clean_docstring(ast.get_docstring(tree))

    imports_set: set[str] = set()
    classes: list[ClassInfo] = []
    functions: list[FunctionInfo] = []
    routes: list[RouteInfo] = []

    for node in tree.body:
        # import a, b as c
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports_set.add(alias.name)

        # from .schema import Manifest or from os import path
        elif isinstance(node, ast.ImportFrom):
            base_mod = node.module
            if node.level and node.level > 0:
                base_mod = _resolve_relative_import(rel_posix_path, node.level, node.module)
            if base_mod:
                imports_set.add(base_mod)
                for alias in node.names:
                    # Also record base_mod.alias so direct submodule imports match
                    imports_set.add(f"{base_mod}.{alias.name}")
            else:
                for alias in node.names:
                    imports_set.add(alias.name)

        # Top-level class
        elif isinstance(node, ast.ClassDef):
            c_info, c_routes = _parse_class(node)
            classes.append(c_info)
            routes.extend(c_routes)

        # Top-level function
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            f_info, f_routes = _parse_function(node)
            functions.append(f_info)
            routes.extend(f_routes)

    return FileAnalysis(
        path=rel_posix_path,
        language="python",
        size=size,
        lines_of_code=lines_of_code,
        module_docstring=module_docstring,
        imports=sorted(imports_set),
        classes=classes,
        functions=functions,
        routes=routes,
    )
