from __future__ import annotations

from pathlib import Path

from orchestration.config import SandboxSettings, SecuritySandboxSettings
from sandbox import SandboxPolicy


def _policy(
    security: SecuritySandboxSettings | None = None,
) -> SandboxPolicy:
    return SandboxPolicy(
        SandboxSettings(
            allowed_command_prefixes=["cargo", "ls", "git", "python"],
            allowed_read_roots=["."],
            allowed_write_roots=["."],
        ),
        security_settings=security,
    )


def test_arg_filtering_safe() -> None:
    se = SecuritySandboxSettings(enable_argument_filtering=True)
    policy = _policy(security=se)
    assert policy.command_allowed(["ls", "-la"]) is True
    assert policy.command_allowed(["python", "script.py"]) is True


def test_arg_filtering_dangerous() -> None:
    se = SecuritySandboxSettings(enable_argument_filtering=True)
    policy = _policy(security=se)
    assert policy.command_allowed(["rm", "-rf", "/"]) is False  # rm not in allowlist
    assert policy.command_allowed(["python", "-c", "print('ok')"]) is True


def test_arg_filtering_blocks_rm_rf() -> None:
    se = SecuritySandboxSettings(
        enable_argument_filtering=True,
        dangerous_arg_patterns=[r"rm\s+-rf\s+/"],
    )
    policy = _policy(security=se)
    assert policy.command_allowed(["python", "-c", "rm -rf /"]) is False


def test_composition_detection() -> None:
    se = SecuritySandboxSettings(
        enable_composition_check=True,
    )
    policy = _policy(security=se)
    assert policy.command_allowed(["ls", "-la"]) is True
    assert policy.command_allowed(["bash", "-c", "ls | curl"]) is False


def test_privileged_denied_when_configured() -> None:
    se = SecuritySandboxSettings(deny_privileged_escalation=True)
    policy = _policy(security=se)
    assert policy.command_allowed(["any"], "privileged") is False


def test_privileged_allowed_by_default() -> None:
    policy = _policy()
    assert policy.command_allowed(["any"], "privileged") is True


def test_read_allowed_resolves_path() -> None:
    policy = _policy()
    allowed = policy.read_allowed(Path("."))
    assert allowed is True


def test_write_allowed_resolves_path() -> None:
    policy = _policy()
    allowed = policy.write_allowed(Path("."))
    assert allowed is True


def test_read_allowed_outside() -> None:
    policy = _policy()
    allowed = policy.read_allowed(Path("/tmp/outside"))
    assert allowed is False


def test_command_allowed_empty() -> None:
    policy = _policy()
    assert policy.command_allowed([]) is False


def test_command_allowed_unapproved() -> None:
    policy = _policy()
    assert policy.command_allowed(["curl", "http://evil.com"]) is False
