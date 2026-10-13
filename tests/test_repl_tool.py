"""Unit tests for Stateful Persistent Python REPL Tool."""

import pytest
from friday.tools.builtin.repl_tool import PythonReplTool


def test_python_repl_variable_persistence():
    """Verify that variables, functions, and state persist across multi-turn calls."""
    repl = PythonReplTool()

    # Step 1: Assign a variable
    r1 = repl.execute("x = 105")
    assert r1["status"] == "success"

    # Step 2: Use previously defined variable in another turn
    r2 = repl.execute("y = x * 2\nprint('Computed y:', y)")
    assert r2["status"] == "success"
    assert "Computed y: 210" in r2["output"]

    # Step 3: Function definition and trailing expression
    r3 = repl.execute("def calc(a, b): return a + b\ncalc(x, y)")
    assert r3["status"] == "success"
    assert "315" in r3["output"]
    assert r3["result"] == "315"


def test_python_repl_pre_imported_math():
    """Verify math, cmath, and statistics are pre-imported in REPL scope."""
    repl = PythonReplTool()

    r = repl.execute("math.sqrt(16) + math.pi > 7")
    assert r["status"] == "success"
    assert "True" in r["output"]


def test_python_repl_security_guard_blocks_os_and_subprocess():
    """Verify security guard blocks dangerous OS calls and subprocess execution."""
    repl = PythonReplTool()

    with pytest.raises(PermissionError) as exc_info:
        repl.execute("import subprocess; subprocess.run(['echo', 'hacked'])")
    assert "restricted in python_repl" in str(exc_info.value)

    with pytest.raises(PermissionError) as exc_info2:
        repl.execute("import os\nos.system('dir')")
    assert "restricted in python_repl" in str(exc_info2.value)


def test_python_repl_syntax_and_runtime_error_handling():
    """Verify clean reporting of syntax and runtime errors."""
    repl = PythonReplTool()

    # Syntax Error
    r1 = repl.execute("def bad_code(:")
    assert r1["status"] == "error"
    assert "SyntaxError" in r1["error"]

    # Runtime Error
    r2 = repl.execute("1 / 0")
    assert r2["status"] == "error"
    assert "ZeroDivisionError" in r2["error"]
