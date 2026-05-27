from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityAuditLogger:
    def __init__(self, log_path: str = ".elyon/security.log", retention_days: int = 90) -> None:
        self._log_path = Path(log_path)
        self._retention_days = retention_days
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        event_type: str,
        *,
        actor: str = "",
        resource: str = "",
        action: str = "",
        decision: str = "",
        reason: str = "",
        details: dict[str, object] | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "actor": actor,
            "resource": resource,
            "action": action,
            "decision": decision,
            "reason": reason,
            "details": details or {},
        }
        line = json.dumps(record, default=str)
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.error("Failed to write security audit log: %s", exc)

    def log_allowed(self, actor: str, resource: str, action: str, details: dict[str, object] | None = None) -> None:
        self.log(
            "SANDBOX_ALLOWED",
            actor=actor,
            resource=resource,
            action=action,
            decision="ALLOW",
            reason="Policy permitted",
            details=details,
        )

    def log_denied(self, actor: str, resource: str, action: str, reason: str, details: dict[str, object] | None = None) -> None:
        self.log(
            "SANDBOX_DENIED",
            actor=actor,
            resource=resource,
            action=action,
            decision="DENY",
            reason=reason,
            details=details,
        )

    def log_key_access(self, provider: str, details: dict[str, object] | None = None) -> None:
        self.log(
            "KEY_ACCESSED",
            actor="provider",
            resource=f"api_key:{provider}",
            action="decrypt",
            decision="ALLOW",
            reason="Provider request",
            details=details,
        )
