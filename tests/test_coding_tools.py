"""Unit tests for Friday's Developer Workspace tools."""

from pathlib import Path
import pytest

from friday.tools.builtin.coding_tools import (
    BashExecuteTool,
    PatchFileTool,
    ReadFileAstTool,
    ReadFileTool,
    WriteFileTool,
)


def test_write_and_read_file(tmp_path: Path):
    writer = WriteFileTool(workspace_dir=str(tmp_path))
    reader = ReadFileTool(workspace_dir=str(tmp_path))

    target = "src/calculator.py"
    content = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"

    # Write file
    write_res = writer.execute(path=target, content=content)
    assert write_res["status"] == "success"
    assert write_res["created"] is True
    assert (tmp_path / target).exists()

    # Read full file
    read_res = reader.execute(path=target)
    assert read_res["total_lines"] == 5
    assert "calculator.py" in read_res["path"]
    assert "add(a, b)" in read_res["raw_content"]

    # Read line slice
    slice_res = reader.execute(path=target, start_line=1, end_line=2)
    assert "add(a, b)" in slice_res["raw_content"]
    assert "sub(a, b)" not in slice_res["raw_content"]


def test_read_file_ast(tmp_path: Path):
    writer = WriteFileTool(workspace_dir=str(tmp_path))
    ast_reader = ReadFileAstTool(workspace_dir=str(tmp_path))

    py_code = (
        "import math\n"
        "from typing import List\n\n"
        "class SignalProcessor:\n"
        "    '''Class for processing continuous signals.'''\n"
        "    def filter(self, data):\n"
        "        pass\n\n"
        "def compute_fft(signal):\n"
        "    '''Compute Fast Fourier Transform.'''\n"
        "    return signal\n"
    )

    writer.execute(path="processor.py", content=py_code)
    ast_res = ast_reader.execute(path="processor.py")

    assert ast_res["syntax_valid"] is True
    assert "math" in ast_res["imports"]
    assert "typing.List" in ast_res["imports"]

    assert len(ast_res["classes"]) == 1
    assert ast_res["classes"][0]["name"] == "SignalProcessor"
    assert "filter" in ast_res["classes"][0]["methods"]

    assert len(ast_res["functions"]) == 1
    assert ast_res["functions"][0]["name"] == "compute_fft"
    assert "signal" in ast_res["functions"][0]["args"]


def test_patch_file(tmp_path: Path):
    writer = WriteFileTool(workspace_dir=str(tmp_path))
    patcher = PatchFileTool(workspace_dir=str(tmp_path))

    original = "def multiply(a, b):\n    return a - b\n"
    writer.execute(path="math_bug.py", content=original)

    # Patch bug
    patch_res = patcher.execute(
        path="math_bug.py",
        target="return a - b",
        replacement="return a * b",
    )
    assert patch_res["status"] == "success"
    assert patch_res["patched"] is True

    # Verify content updated
    patched_content = (tmp_path / "math_bug.py").read_text(encoding="utf-8")
    assert "return a * b" in patched_content
    assert "return a - b" not in patched_content

    # Target not found raises ValueError
    with pytest.raises(ValueError):
        patcher.execute(
            path="math_bug.py",
            target="def nonexistent():",
            replacement="pass",
        )


def test_bash_execute(tmp_path: Path):
    executor = BashExecuteTool(workspace_dir=str(tmp_path))

    # Safe PowerShell echo test
    res = executor.execute(command='Write-Output "Friday Terminal Nominal"')
    assert res["success"] is True
    assert res["exit_code"] == 0
    assert "Friday Terminal Nominal" in res["stdout"]
