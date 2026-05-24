from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdapterContext:
    prompt: str
    model: str | None = None
    files: list[str] | None = None
    extra_args: dict[str, Any] | None = None


class AbstractAgentAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The canonical name of the agent this adapter handles."""
        pass

    @abstractmethod
    def build_command(self, binary: str, context: AdapterContext) -> list[str]:
        """Construct the full shell command for the agent."""
        pass

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str) -> str:
        """Extract the meaningful response from the agent's raw output."""
        pass

    def detect_failure(self, exit_code: int, stdout: str, stderr: str) -> bool:
        """Identify if the agent failed in a way that requires specific recovery."""
        return exit_code != 0
