from __future__ import annotations

from pathlib import Path


def execute(output_path: Path, *, force: bool) -> dict[str, object]:
    if output_path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing config without --force: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_template(), encoding="utf-8")

    return {
        "status": "ok",
        "message": "Config initialized",
        "path": str(output_path),
    }


def _template() -> str:
    return """default_provider = "local_mock"

[providers.local_mock]
name = "local_mock"
base_url = ""
model = "local-model"
default_temperature = 0.0
default_max_tokens = 1024
timeout_seconds = 15.0
max_retries = 0
api_key_env = ""

[agents.planner]
name = "planner"
role = "planner"
provider = "local_mock"
model = "local-model"
description = "Plans and decomposes tasks"

[agents.repairer]
name = "repairer"
role = "repairer"
provider = "local_mock"
model = "local-model"
description = "Fixes code issues based on compiler diagnostics"

[agents.verifier]
name = "verifier"
role = "verifier"
provider = "local_mock"
model = "local-model"
description = "Verifies that repairs are correct"

[runtime]
command = ["runtime/target/release/elyon-runtime"]
request_timeout_seconds = 60.0
max_stdout_bytes = 1048576
max_stderr_bytes = 1048576

[repair]
max_attempts = 3
verify_after_repair = true
allowed_extensions = [".py", ".rs", ".toml"]

[telemetry]
log_level = "INFO"
json_logs = true

[sandbox]
allowed_command_prefixes = ["cargo", "pytest", "ruff", "mypy", "opencode", "aider", "claude", "codex", "gemini"]
allowed_read_roots = ["."]
allowed_write_roots = ["."]

[state]
event_log_path = "./state/events.jsonl"
"""
