from __future__ import annotations

from orchestration.adapters.base import AbstractAgentAdapter, AdapterContext


class DefaultAdapter(AbstractAgentAdapter):
    @property
    def name(self) -> str:
        return "default"

    def build_command(self, binary: str, context: AdapterContext) -> list[str]:
        return [binary, context.prompt]

    def parse_output(self, stdout: str, stderr: str) -> str:
        return stdout.strip()


class AiderAdapter(AbstractAgentAdapter):
    @property
    def name(self) -> str:
        return "aider"

    def build_command(self, binary: str, context: AdapterContext) -> list[str]:
        return [binary, "--message", context.prompt]

    def parse_output(self, stdout: str, stderr: str) -> str:
        return stdout.strip()


class ClaudeAdapter(AbstractAgentAdapter):
    @property
    def name(self) -> str:
        return "claude"

    def build_command(self, binary: str, context: AdapterContext) -> list[str]:
        return [binary, "-p", context.prompt]

    def parse_output(self, stdout: str, stderr: str) -> str:
        return stdout.strip()


class OllamaAdapter(AbstractAgentAdapter):
    @property
    def name(self) -> str:
        return "ollama"

    def build_command(self, binary: str, context: AdapterContext) -> list[str]:
        model = context.model or "default"
        return [binary, "run", model, context.prompt]

    def parse_output(self, stdout: str, stderr: str) -> str:
        return stdout.strip()


_ADAPTERS: dict[str, type[AbstractAgentAdapter]] = {
    "aider": AiderAdapter,
    "claude": ClaudeAdapter,
    "claude.exe": ClaudeAdapter,
    "ollama": OllamaAdapter,
}


def get_adapter(binary: str) -> AbstractAgentAdapter:
    import os

    basename = os.path.basename(binary.lower())
    adapter_cls = _ADAPTERS.get(basename, DefaultAdapter)
    return adapter_cls()
