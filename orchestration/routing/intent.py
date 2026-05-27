from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal


class Intent(StrEnum):
    SHELL_COMMAND = "shell_command"
    FILE_OPERATION = "file_operation"
    EXPLANATION = "explanation"
    CODE_GENERATION = "code_generation"
    DEBUGGING = "debugging"
    PROJECT_QUERY = "project_query"
    AMBIGUOUS = "ambiguous"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    command: str | None = None
    file_path: str | None = None
    prompt: str | None = None


SHELL_PATTERNS: list[tuple[re.Pattern, str | None]] = [
    (re.compile(r"^(list|ls|show)\s+(files?|dir|directory)", re.I), "ls -la"),
    (re.compile(r"^(list|ls|show)\s+(all\s+)?(files?|dir)", re.I), "ls -la"),
    (re.compile(r"^ls\s+", re.I), None),
    (re.compile(r"^(git|hg|svn)\s+", re.I), None),
    (re.compile(r"^(find|grep|search)\s+", re.I), None),
    (re.compile(r"^(cd|pwd|whoami|date|uptime|uname)$", re.I), None),
    (re.compile(r"^(count|wc)\s+(lines|words)\s+", re.I), "wc"),
    (re.compile(r"^(disk|df|du)\s+", re.I), None),
    (re.compile(r"^(mkdir|rmdir|touch|cp|mv|rm)\s+", re.I), None),
    (re.compile(r"^(which|type|whereis|whatis)\s+", re.I), None),
    (re.compile(r"^(cat|head|tail|less|more)\s+", re.I), None),
]

FILE_OP_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(read|show|cat|print|get|open|view)\s+(file\s+)?", re.I),
    re.compile(r"^(head|tail)\s+", re.I),
    re.compile(r"^(count|wc)\s+(lines|words)", re.I),
    re.compile(r"^(list|ls|show)\s+(files?|dir)", re.I),
]

EXPLANATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(explain|what is|describe|how does|what does|why does)", re.I),
    re.compile(r"^(summarize|overview|tell me about)", re.I),
    re.compile(r".*\?\s*$", re.I),
]

CODE_GEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(write|create|implement|generate|build|make|add)", re.I),
    re.compile(r"^(refactor|rewrite|convert|migrate)", re.I),
    re.compile(r"^(add|implement)\s+(feature|function|class|test)", re.I),
]

DEBUG_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(fix|debug|repair|correct|resolve|solve)", re.I),
    re.compile(r"(error|bug|issue|problem|fail|broken|crash)", re.I),
    re.compile(r"(traceback|exception|panic|segfault)", re.I),
]


class IntentRouter:
    def __init__(
        self,
        *,
        enabled: bool = True,
        confidence_threshold: float = 0.7,
        enable_shell_commands: bool = True,
        enable_file_operations: bool = True,
    ) -> None:
        self._enabled = enabled
        self._confidence_threshold = confidence_threshold
        self._enable_shell_commands = enable_shell_commands
        self._enable_file_operations = enable_file_operations

    def classify(self, prompt: str) -> IntentResult:
        if not self._enabled or not prompt.strip():
            return IntentResult(
                intent=Intent.AMBIGUOUS,
                confidence=0.0,
                prompt=prompt,
            )

        stripped = prompt.strip()
        result = self._classify_pattern(stripped)
        if result.confidence >= self._confidence_threshold:
            return result

        return IntentResult(
            intent=Intent.AMBIGUOUS,
            confidence=result.confidence,
            prompt=stripped,
        )

    def _classify_pattern(self, prompt: str) -> IntentResult:
        if self._enable_shell_commands:
            for pattern, command in SHELL_PATTERNS:
                match = pattern.match(prompt)
                if match:
                    cmd = command or match.group(0).strip().split()[0]
                    return IntentResult(
                        intent=Intent.SHELL_COMMAND,
                        confidence=0.95,
                        command=cmd,
                        prompt=prompt,
                    )

        if self._enable_file_operations:
            for pattern in FILE_OP_PATTERNS:
                if pattern.match(prompt):
                    path = self._extract_file_path(prompt)
                    return IntentResult(
                        intent=Intent.FILE_OPERATION,
                        confidence=0.9,
                        file_path=path,
                        prompt=prompt,
                    )

        for pattern in DEBUG_PATTERNS:
            if pattern.search(prompt):
                return IntentResult(
                    intent=Intent.DEBUGGING,
                    confidence=0.85,
                    prompt=prompt,
                )

        for pattern in CODE_GEN_PATTERNS:
            if pattern.match(prompt):
                return IntentResult(
                    intent=Intent.CODE_GENERATION,
                    confidence=0.8,
                    prompt=prompt,
                )

        for pattern in EXPLANATION_PATTERNS:
            if pattern.match(prompt):
                return IntentResult(
                    intent=Intent.EXPLANATION,
                    confidence=0.75,
                    prompt=prompt,
                )

        return IntentResult(
            intent=Intent.AMBIGUOUS,
            confidence=0.0,
            prompt=prompt,
        )

    @staticmethod
    def _extract_file_path(prompt: str) -> str | None:
        words = prompt.strip().split()
        for word in words:
            word = word.strip(".,;:!?\"'")
            if "/" in word or word.endswith((".py", ".rs", ".js", ".ts", ".go", ".md", ".toml", ".json", ".yaml", ".yml")):
                return word
            if word.startswith("/") or word.startswith("./") or word.startswith("../"):
                return word
        return None

    def translate_to_shell(self, prompt: str) -> str:
        for pattern, command in SHELL_PATTERNS:
            match = pattern.match(prompt.strip())
            if match:
                if command:
                    rest = prompt[match.end():].strip()
                    return f"{command} {rest}" if rest else command
                return match.group(0).strip()
        return prompt
