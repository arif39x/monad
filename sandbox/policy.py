from __future__ import annotations

from pathlib import Path

from orchestration.config import SandboxSettings


class SandboxPolicy:
    def __init__(self, settings: SandboxSettings) -> None:
        self._settings = settings

    def command_allowed(self, command: list[str], policy_level: str = "standard") -> bool:
        if not command:
            return False
        
        if policy_level.lower() == "privileged":
            return True
            
        executable = command[0]
        import os
        exe_name = os.path.basename(executable)
        
        for prefix in self._settings.allowed_command_prefixes:
            if exe_name == prefix or executable == prefix:
                return True
                
        if policy_level.lower() == "restricted":
            return False
            
        return False

    def read_allowed(self, path: Path, policy_level: str = "standard") -> bool:
        if policy_level.lower() == "privileged":
            return True
        resolved = path.resolve()
        return _is_in_roots(resolved, self._settings.allowed_read_roots)

    def write_allowed(self, path: Path, policy_level: str = "standard") -> bool:
        if policy_level.lower() == "privileged":
            return True
        resolved = path.resolve()
        return _is_in_roots(resolved, self._settings.allowed_write_roots)


def _is_in_roots(path: Path, roots: list[str]) -> bool:
    for root in roots:
        candidate = Path(root).resolve()
        if path == candidate or candidate in path.parents:
            return True
    return False
