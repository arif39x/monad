from __future__ import annotations

import json
from pathlib import Path

from sandbox.audit import SecurityAuditLogger


def test_audit_log_allowed(tmp_path: Path) -> None:
    log_path = str(tmp_path / "security.log")
    logger = SecurityAuditLogger(log_path=log_path)
    logger.log_allowed(
        actor="planner",
        resource="cmd:ls",
        action="execute",
        details={"command": ["ls", "-la"]},
    )
    lines = Path(log_path).read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "SANDBOX_ALLOWED"
    assert record["actor"] == "planner"
    assert record["decision"] == "ALLOW"


def test_audit_log_denied(tmp_path: Path) -> None:
    log_path = str(tmp_path / "security.log")
    logger = SecurityAuditLogger(log_path=log_path)
    logger.log_denied(
        actor="planner",
        resource="cmd:rm",
        action="execute",
        reason="Dangerous arguments",
    )
    lines = Path(log_path).read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "SANDBOX_DENIED"
    assert record["decision"] == "DENY"
    assert record["reason"] == "Dangerous arguments"


def test_audit_log_key_access(tmp_path: Path) -> None:
    log_path = str(tmp_path / "security.log")
    logger = SecurityAuditLogger(log_path=log_path)
    logger.log_key_access("openai", details={"key_prefix": "sk-..."})
    lines = Path(log_path).read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "KEY_ACCESSED"


def test_audit_log_custom_event(tmp_path: Path) -> None:
    log_path = str(tmp_path / "security.log")
    logger = SecurityAuditLogger(log_path=log_path)
    logger.log(
        "PRIVILEGE_ESCALATION",
        actor="agent_x",
        resource="policy_level",
        action="request",
        decision="DENY",
        reason="Not authorized",
    )
    lines = Path(log_path).read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "PRIVILEGE_ESCALATION"


def test_audit_log_multiple_events(tmp_path: Path) -> None:
    log_path = str(tmp_path / "security.log")
    logger = SecurityAuditLogger(log_path=log_path)
    logger.log_allowed(actor="a", resource="r1", action="exec")
    logger.log_denied(actor="b", resource="r2", action="exec", reason="blocked")
    lines = Path(log_path).read_text().strip().splitlines()
    assert len(lines) == 2
