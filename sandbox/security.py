from __future__ import annotations

import re
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_per_minute: int = 30, burst: int = 5) -> None:
        self._max_per_minute = max_per_minute
        self._burst = burst
        self._tokens: dict[str, float] = defaultdict(float)
        self._last_refill: dict[str, float] = defaultdict(float)

    def check(self, key: str = "default") -> bool:
        now = time.time()
        refill = self._last_refill.get(key, now)
        elapsed = now - refill
        tokens_to_add = elapsed * (self._max_per_minute / 60.0)
        current = min(self._burst, self._tokens.get(key, self._burst) + tokens_to_add)
        self._last_refill[key] = now

        if current >= 1.0:
            self._tokens[key] = current - 1.0
            return True

        self._tokens[key] = current
        return False

    def remaining(self, key: str = "default") -> float:
        return self._tokens.get(key, self._burst)


class NetworkPolicy:
    def __init__(
        self,
        enabled: bool = False,
        allowed_hosts: list[str] | None = None,
    ) -> None:
        self._enabled = enabled
        self._allowed_hosts = set(allowed_hosts or [])

    @property
    def enabled(self) -> bool:
        return self._enabled

    def check_egress(self, command: list[str]) -> bool:
        if not self._enabled:
            return True

        executable = command[0] if command else ""
        network_tools = {"curl", "wget", "nc", "ncat", "ssh", "scp", "telnet", "ftp"}

        if executable not in network_tools:
            return True

        for arg in command[1:]:
            if arg.startswith("http://") or arg.startswith("https://"):
                host = self._extract_host(arg)
                if host and not self._host_allowed(host):
                    return False
            if "@" in arg and ("." in arg.split("@")[-1] or ":" in arg.split("@")[-1]):
                parts = arg.split("@")
                if len(parts) > 1:
                    host_part = parts[-1].split(":")[0]
                    if not self._host_allowed(host_part):
                        return False

        return True

    def _extract_host(self, url: str) -> str | None:
        match = re.match(r"https?://([^/:]+)", url)
        return match.group(1) if match else None

    def _host_allowed(self, host: str) -> bool:
        if not self._allowed_hosts:
            return False
        for allowed in self._allowed_hosts:
            if host == allowed or host.endswith("." + allowed):
                return True
        return False
