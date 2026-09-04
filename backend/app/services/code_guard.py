"""Static (AST) validation of LLM-generated code, run before the sandbox.

This is layer 1 of the sandbox. It rejects whole *categories* of syntax rather
than matching substrings, so `"__cla" + "ss__"` and other string tricks that
defeat a token blacklist do not get past it:

- no `import` of any kind
- no attribute whose name starts with `_` (kills `().__class__.__base__
  .__subclasses__()`, `.__globals__`, `._module`, and every other private hop)
- no `.format`/`.format_map`, which perform the same hops from inside a string
- no name starting with `__` (kills `__builtins__`, `__import__`)
- no calls to introspection/eval builtins (`getattr`, `eval`, `open`, ...)
- no pandas reader/writer methods (`df.to_csv`, `pd.read_csv`, ...), which touch
  the filesystem without needing a single dunder

It is NOT a security boundary on its own -- see SECURITY.md. The runtime
restrictions in `_sandbox_runner.py` and the OS limits in `_limits.py` are the
other two layers, and the production answer is an OS-level container.
"""
from __future__ import annotations

import ast

# Builtins and helpers that let code escape the restricted namespace or reach
# the interpreter. `getattr`/`hasattr` matter most: they turn any runtime string
# into an attribute access, which would sidestep every rule below.
DENIED_NAMES = frozenset({
    "__import__", "breakpoint", "classmethod", "compile", "delattr", "dir",
    "eval", "exec", "exit", "getattr", "globals", "hasattr", "help", "input",
    "locals", "memoryview", "object", "open", "property", "quit", "setattr",
    "staticmethod", "super", "type", "vars",
})

# Attribute names that reach the filesystem, a database, or an expression
# evaluator. Note `to_datetime`/`to_numeric`/`to_dict`/`to_numpy` are *not*
# here -- they are ordinary, common analysis calls.
DENIED_ATTRS = frozenset({
    # writers (filesystem / network / clipboard)
    "to_clipboard", "to_csv", "to_excel", "to_feather", "to_gbq", "to_hdf",
    "to_json", "to_latex", "to_orc", "to_parquet", "to_pickle", "to_sql",
    "to_stata", "to_xml",
    # expression evaluators -- `df.query`/`df.eval` compile strings at runtime
    "eval", "query",
    # class-hierarchy walking and template engines
    "mro", "style", "plot",
    # `"{0.__class__.__init__.__globals__[sys]}".format(df)` walks the object
    # graph entirely inside a *string literal*, so the private-attribute rule
    # below never sees an ast.Attribute node to reject. f-strings are already
    # covered -- they compile to real attribute accesses -- but these two are
    # the interpreter's own string-driven getattr and must be named.
    "format", "format_map",
})

# Any attribute starting with one of these prefixes is denied.
DENIED_ATTR_PREFIXES = ("read_",)


class CodeRejected(Exception):
    """Raised when generated code violates a sandbox rule."""


def _fail(node: ast.AST, message: str) -> CodeRejected:
    line = getattr(node, "lineno", None)
    where = f" (line {line})" if line else ""
    return CodeRejected(f"{message}{where}")


def validate(code: str) -> None:
    """Raise CodeRejected if `code` breaks a rule. Return None if it is fine."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeRejected(f"Code is not valid Python: {exc.msg} (line {exc.lineno})")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise _fail(node, "imports are not allowed; use `df` and `pd` only")

        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("_"):
                raise _fail(node, f"access to private attribute `{attr}` is not allowed")
            if attr in DENIED_ATTRS:
                raise _fail(node, f"`{attr}` is not allowed in the sandbox")
            if attr.startswith(DENIED_ATTR_PREFIXES):
                raise _fail(node, f"`{attr}` reads from disk, which is not allowed")

        elif isinstance(node, ast.Name):
            name = node.id
            if name.startswith("__"):
                raise _fail(node, f"access to `{name}` is not allowed")
            if name in DENIED_NAMES:
                raise _fail(node, f"`{name}` is not allowed in the sandbox")

        # `del x`, `global x` etc. cannot reach anything, but attribute
        # deletion on pandas internals is pointless and worth refusing.
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise _fail(node, "`global`/`nonlocal` are not allowed")


def check(code: str) -> str | None:
    """Return an error message for the retry loop, or None if `code` is clean."""
    try:
        validate(code)
    except CodeRejected as exc:
        return (
            f"Code rejected by the sandbox: {exc}. "
            "Rewrite it using only pandas operations on the existing `df`."
        )
    return None
