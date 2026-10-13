"""Unit tests for Friday Structured Audit Logger and Secret Redactor."""

import json
import tempfile
from pathlib import Path
import pytest

from friday.security.audit import AuditLogger, redact_secrets, redact_dict
from friday.tools.builtin.coding_tools import (
    ReadFileTool,
    WriteFileTool,
    PatchFileTool,
    ReadFileAstTool,
)


def test_redact_secrets_gemini_and_openai():
    """Verify API keys and bearer tokens are masked."""
    gemini_key = "AIzaSyD" + "0123456789abcdef0123456789abcde"
    openai_key = "sk-1234567890abcdef1234567890"
    bearer = "Bearer ya29.a0ARrdaM8sampletoken123"
    env_str = "GEMINI_API_KEY='super_secret_val'\nPASSWORD=mypass"

    sample = f"Keys: {gemini_key}, {openai_key}, {bearer}\n{env_str}"
    scrubbed = redact_secrets(sample)

    assert gemini_key not in scrubbed
    assert openai_key not in scrubbed
    assert "ya29" not in scrubbed
    assert "[REDACTED_GEMINI_KEY]" in scrubbed
    assert "[REDACTED_OPENAI_KEY]" in scrubbed
    assert "Bearer [REDACTED_TOKEN]" in scrubbed
    assert "GEMINI_API_KEY=[REDACTED_SECRET]" in scrubbed
    assert "PASSWORD=[REDACTED_SECRET]" in scrubbed


def test_redact_dict_recursive():
    """Verify nested dictionary payloads are scrubbed."""
    payload = {
        "user": "developer",
        "nested": {
            "token": "sk-1234567890abcdef1234567890",
            "list": ["AIzaSyD0123456789abcdef0123456789abcde", "normal_data"],
        },
    }
    cleaned = redact_dict(payload)
    assert cleaned["nested"]["token"] == "[REDACTED_OPENAI_KEY]"
    assert cleaned["nested"]["list"][0] == "[REDACTED_GEMINI_KEY]"
    assert cleaned["nested"]["list"][1] == "normal_data"


def test_audit_logger_writes_jsonl():
    """Verify AuditLogger writes structured, sanitized JSONL entries to disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        logger = AuditLogger(log_dir=tmp_dir)
        key = "AIzaSyD0123456789abcdef0123456789abcde"

        entry = logger.log_execution(
            tool_name="write_file",
            tier="REVERSIBLE",
            parameters={"path": "vault/test.md", "content": f"key={key}"},
            latency_ms=14.5,
            success=True,
        )

        assert entry["tool_name"] == "write_file"
        assert entry["tier"] == "REVERSIBLE"
        assert "[REDACTED_GEMINI_KEY]" in entry["parameters"]["content"]

        log_file = Path(tmp_dir) / "audit.jsonl"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["latency_ms"] == 14.5
        assert parsed["success"] is True


def test_env_file_blocking_across_tools():
    """Verify ReadFile, WriteFile, PatchFile, and ReadFileAst strictly block access to .env."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        env_file = Path(tmp_dir) / ".env"
        env_file.write_text("GEMINI_API_KEY=test_key\n", encoding="utf-8")

        r_tool = ReadFileTool(workspace_dir=tmp_dir)
        ast_tool = ReadFileAstTool(workspace_dir=tmp_dir)
        w_tool = WriteFileTool(workspace_dir=tmp_dir)
        p_tool = PatchFileTool(workspace_dir=tmp_dir)

        with pytest.raises(PermissionError, match=r"\.env"):
            r_tool.execute(".env")

        with pytest.raises(PermissionError, match=r"\.env"):
            ast_tool.execute(".env")

        with pytest.raises(PermissionError, match=r"\.env"):
            w_tool.execute(".env", "HACKED=1")

        with pytest.raises(PermissionError, match=r"\.env"):
            p_tool.execute(".env", target="test", replacement="hacked")
