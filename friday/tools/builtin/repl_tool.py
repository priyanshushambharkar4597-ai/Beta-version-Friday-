"""Stateful Persistent Python REPL Tool for Friday."""

from __future__ import annotations

import ast
import contextlib
import io
import math
import cmath
import statistics
import traceback
from typing import Any, Dict, Optional

from friday.tools.base import BaseTool, PermissionTier

# Attempt numpy import
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

RESTRICTED_KEYWORDS = {
    "os.system",
    "subprocess",
    "socket.socket",
    "shutil.rmtree",
    "sys.exit",
    "ctypes",
}


class PythonReplTool(BaseTool):
    """Persistent, stateful in-process Python REPL tool.

    Allows multi-turn variable state, mathematical calculations, and scientific
    modeling while maintaining safe sandbox guardrails against destructive OS operations.
    """

    name = "python_repl"
    description = (
        "Execute Python code in a persistent stateful REPL environment. Variables, "
        "functions, and imports persist across calls. Output from print() and trailing "
        "expressions are captured."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self) -> None:
        """Initialize the persistent REPL environment."""
        self.scope: Dict[str, Any] = {}
        self.reset()

    def reset(self) -> None:
        """Reset the REPL scope to clean default environment."""
        self.scope = {
            "math": math,
            "cmath": cmath,
            "statistics": statistics,
        }
        if _HAS_NUMPY:
            self.scope["np"] = np
            self.scope["numpy"] = np

    def _check_security(self, code: str) -> None:
        """Check for prohibited dangerous OS/subprocess calls."""
        for restricted in RESTRICTED_KEYWORDS:
            if restricted in code:
                raise PermissionError(
                    f"Direct OS process execution or socket operations ('{restricted}') "
                    f"are restricted in python_repl. Use the bash_execute tool instead."
                )

        # AST inspection for import of restricted modules
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ("subprocess", "socket", "ctypes"):
                            raise PermissionError(
                                f"Importing '{alias.name}' is restricted in python_repl. "
                                f"Use the bash_execute tool instead."
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module in ("subprocess", "socket", "ctypes"):
                        raise PermissionError(
                            f"Importing from '{node.module}' is restricted in python_repl. "
                            f"Use the bash_execute tool instead."
                        )
        except SyntaxError:
            pass

    def execute(self, code: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute code within the persistent stateful scope.

        Args:
            code: Python code string to execute.

        Returns:
            Dictionary containing execution status, stdout output, result expression, and errors.
        """
        self._check_security(code)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            tree = ast.parse(code)
        except SyntaxError as syn_err:
            return {
                "status": "error",
                "error": f"SyntaxError: {syn_err}",
                "output": "",
            }

        expr_result: Any = None
        has_trailing_expr = bool(tree.body and isinstance(tree.body[-1], ast.Expr))

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                if has_trailing_expr:
                    # Execute all preceding statements
                    if len(tree.body) > 1:
                        mod_body = ast.Module(body=tree.body[:-1], type_ignores=[])
                        compiled_body = compile(mod_body, filename="<repl>", mode="exec")
                        exec(compiled_body, self.scope, self.scope)

                    # Evaluate the final expression
                    expr_stmt = tree.body[-1]
                    assert isinstance(expr_stmt, ast.Expr)
                    expr_mod = ast.Expression(body=expr_stmt.value)
                    compiled_expr = compile(expr_mod, filename="<repl>", mode="eval")
                    expr_result = eval(compiled_expr, self.scope, self.scope)
                    if expr_result is not None:
                        print(repr(expr_result))
                else:
                    compiled_mod = compile(tree, filename="<repl>", mode="exec")
                    exec(compiled_mod, self.scope, self.scope)

            except Exception as exc:
                return {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {str(exc)}",
                    "output": stdout_buf.getvalue(),
                    "traceback": traceback.format_exc(),
                }

        stdout_str = stdout_buf.getvalue()
        stderr_str = stderr_buf.getvalue()

        return {
            "status": "success",
            "output": stdout_str + (f"\n[stderr]: {stderr_str}" if stderr_str else ""),
            "result": str(expr_result) if expr_result is not None else None,
        }
