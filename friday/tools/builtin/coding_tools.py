"""Developer Workspace Tools - Agentic Coding Suite for Friday."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from friday.tools.base import BaseTool, PermissionTier


def _resolve_safe_path(path: str, base_dir: Optional[str] = None) -> Path:
    """Resolve path safely relative to base directory or current workspace."""
    base = Path(base_dir or os.getcwd()).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = (base / target).resolve()
    return target


class ReadFileTool(BaseTool):
    """Tool to read file contents from the local filesystem."""

    name = "read_file"
    description = (
        "Read content of a file from the filesystem. Supports optional start_line "
        "and end_line range (1-indexed)."
    )
    tier = PermissionTier.READ

    def __init__(self, workspace_dir: Optional[str] = None) -> None:
        self.workspace_dir = workspace_dir

    def execute(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = _resolve_safe_path(path, self.workspace_dir)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if target.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        raw = target.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines(keepends=True)
        total_lines = len(lines)

        s = (start_line - 1) if (start_line and start_line > 0) else 0
        e = end_line if (end_line and end_line > 0) else total_lines

        selected = lines[s:e]
        content_with_nums = "".join(
            [f"{s + idx + 1:4d} | {line}" for idx, line in enumerate(selected)]
        )

        return {
            "path": str(target),
            "total_lines": total_lines,
            "start_line": s + 1,
            "end_line": min(e, total_lines),
            "content": content_with_nums,
            "raw_content": "".join(selected),
        }


class ReadFileAstTool(BaseTool):
    """Tool to parse Python files using AST for token-efficient code understanding."""

    name = "read_file_ast"
    description = (
        "Parse a Python file using AST to extract top-level classes, functions, "
        "method signatures, docstrings, and imports."
    )
    tier = PermissionTier.READ

    def __init__(self, workspace_dir: Optional[str] = None) -> None:
        self.workspace_dir = workspace_dir

    def execute(self, path: str, **kwargs: Any) -> Dict[str, Any]:
        target = _resolve_safe_path(path, self.workspace_dir)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")

        source = target.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(target))
        except SyntaxError as syn_err:
            return {
                "path": str(target),
                "syntax_valid": False,
                "error": f"SyntaxError: {syn_err}",
            }

        imports: List[str] = []
        classes: List[Dict[str, Any]] = []
        functions: List[Dict[str, Any]] = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append(f"{mod}.{alias.name}")
            elif isinstance(node, ast.ClassDef):
                methods = [
                    m.name
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "docstring": ast.get_docstring(node),
                    "methods": methods,
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "docstring": ast.get_docstring(node),
                    "args": [a.arg for a in node.args.args],
                })

        return {
            "path": str(target),
            "syntax_valid": True,
            "imports": imports,
            "classes": classes,
            "functions": functions,
        }


class WriteFileTool(BaseTool):
    """Tool to create or overwrite a file with given content."""

    name = "write_file"
    description = (
        "Create or overwrite a file on the local filesystem. Automatically creates "
        "parent directories if they do not exist."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self, workspace_dir: Optional[str] = None) -> None:
        self.workspace_dir = workspace_dir

    def execute(self, path: str, content: str, **kwargs: Any) -> Dict[str, Any]:
        target = _resolve_safe_path(path, self.workspace_dir)
        target.parent.mkdir(parents=True, exist_ok=True)

        existed = target.exists()
        previous_content = None
        if existed:
            previous_content = target.read_text(encoding="utf-8", errors="replace")

        target.write_text(content, encoding="utf-8")

        return {
            "status": "success",
            "path": str(target),
            "created": not existed,
            "bytes_written": len(content.encode("utf-8")),
            "backup_available": existed,
            "previous_content_length": len(previous_content) if previous_content else 0,
        }


class PatchFileTool(BaseTool):
    """Tool to patch specific text chunks in an existing file."""

    name = "patch_file"
    description = (
        "Patch an existing file by replacing exact target text with replacement text. "
        "Fails if target text is not found or occurs multiple times ambiguously."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self, workspace_dir: Optional[str] = None) -> None:
        self.workspace_dir = workspace_dir

    def execute(
        self,
        path: str,
        target: str,
        replacement: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target_path = _resolve_safe_path(path, self.workspace_dir)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found to patch: {path}")

        content = target_path.read_text(encoding="utf-8", errors="replace")

        count = content.count(target)
        if count == 0:
            raise ValueError(f"Target text not found in {path}")
        if count > 1:
            raise ValueError(
                f"Target text found {count} times in {path}. Provide a more specific target block."
            )

        patched = content.replace(target, replacement, 1)
        target_path.write_text(patched, encoding="utf-8")

        return {
            "status": "success",
            "path": str(target_path),
            "patched": True,
            "replaced_bytes": len(target.encode("utf-8")),
            "new_bytes": len(replacement.encode("utf-8")),
        }


class BashExecuteTool(BaseTool):
    """Tool to execute terminal and shell commands locally."""

    name = "bash_execute"
    description = (
        "Execute a terminal shell command (PowerShell on Windows, Bash on Unix). "
        "Classified as IRREVERSIBLE and requires explicit CLI confirmation."
    )
    tier = PermissionTier.IRREVERSIBLE

    def __init__(self, workspace_dir: Optional[str] = None) -> None:
        self.workspace_dir = workspace_dir

    def execute(
        self,
        command: str,
        timeout: int = 60,
        cwd: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        working_dir = _resolve_safe_path(cwd or ".", self.workspace_dir)

        # Use powershell.exe on Windows for native syntax compatibility
        if sys.platform == "win32":
            shell_cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
        else:
            shell_cmd = ["/bin/bash", "-c", command]

        try:
            proc = subprocess.run(
                shell_cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "command": command,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "success": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds.",
                "success": False,
            }
        except Exception as exc:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "success": False,
            }
