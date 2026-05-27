from __future__ import annotations

import os
import re
from pathlib import Path

from orchestration.config import SandboxSettings, SecuritySandboxSettings


class SandboxPolicy:
    def __init__(
        self,
        settings: SandboxSettings,
        security_settings: SecuritySandboxSettings | None = None,
    ) -> None:
        self._settings = settings
        self._security = security_settings or SecuritySandboxSettings()
        self._dangerous_patterns = [
            re.compile(p, re.I) for p in self._security.dangerous_arg_patterns
        ]

    def command_allowed(self, command: list[str], policy_level: str = "standard") -> bool:
        if not command:
            return False

        if policy_level.lower() == "privileged":
            if self._security.deny_privileged_escalation:
                return False
            return True

        executable = command[0]
        exe_name = os.path.basename(executable)

        allowed = False
        for prefix in self._settings.allowed_command_prefixes:
            if exe_name == prefix or executable == prefix:
                allowed = True
                break

        if not allowed:
            return False

        if policy_level.lower() == "restricted":
            return False

        if self._security.enable_argument_filtering and len(command) > 1:
            full_cmd = " ".join(command)
            for pattern in self._dangerous_patterns:
                if pattern.search(full_cmd):
                    return False

        if self._security.enable_composition_check and len(command) > 1:
            full_cmd = " ".join(command)
            if self._has_shell_composition(full_cmd):
                return False

        return True

    def read_allowed(self, path: Path, policy_level: str = "standard") -> bool:
        if policy_level.lower() == "privileged":
            if self._security.deny_privileged_escalation:
                return False
            return True
        resolved = self._resolve_path(path)
        return _is_in_roots(resolved, self._settings.allowed_read_roots)

    def write_allowed(self, path: Path, policy_level: str = "standard") -> bool:
        if policy_level.lower() == "privileged":
            if self._security.deny_privileged_escalation:
                return False
            return True
        resolved = self._resolve_path(path)
        return _is_in_roots(resolved, self._settings.allowed_write_roots)

    def _resolve_path(self, path: Path) -> Path:
        try:
            return path.resolve(strict=False)
        except OSError:
            return path.resolve()

    def _has_shell_composition(self, cmd: str) -> bool:
        composition_patterns = [
            re.compile(r"\|"),
            re.compile(r"`[^`]+`"),
            re.compile(r"\$\([^)]+\)"),
            re.compile(r";\s*"),
        ]
        for pattern in composition_patterns:
            if pattern.search(cmd):
                return True
        return False


def _is_in_roots(path: Path, roots: list[str]) -> bool:
    for root in roots:
        candidate = Path(root).resolve()
        if path == candidate or candidate in path.parents:
            return True
    return False
