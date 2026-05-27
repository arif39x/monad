from __future__ import annotations

import json
import re
from dataclasses import dataclass

from orchestration.minify.token_counter import TokenCounter


@dataclass(frozen=True)
class MinificationReport:
    original_tokens: int
    final_tokens: int
    ratio: float
    stages_applied: tuple[str, ...] = ()


WHITESPACE_PATTERN = re.compile(r"\n{3,}")
TRAILING_SPACE_PATTERN = re.compile(r"[ \t]+$", re.MULTILINE)
FILE_LABEL_PATTERN = re.compile(
    r"File:\s*(?:/[\w.\-/]*?)?([\w.\- ]+\.\w+)\s*\nContent:",
    re.MULTILINE,
)
JSON_PATTERN = re.compile(r"(\{.*\}|\[.*\])\s*$", re.DOTALL)
SYSTEM_PROMPT_PATTERN = re.compile(
    r"(?i)(system|instructions?|context):?\s*",
)


class PromptMinifier:
    def __init__(
        self,
        *,
        enabled: bool = True,
        target_tokens: int = 4096,
        hard_limit: int = 8192,
        preserve_user_message: bool = True,
        structural_only: bool = False,
    ) -> None:
        self._enabled = enabled
        self._target_tokens = target_tokens
        self._hard_limit = hard_limit
        self._preserve_user_message = preserve_user_message
        self._structural_only = structural_only
        self._token_counter = TokenCounter()

    def minify(self, prompt: str) -> tuple[str, MinificationReport]:
        if not self._enabled or not prompt:
            report = MinificationReport(
                original_tokens=0,
                final_tokens=0,
                ratio=1.0,
                stages_applied=(),
            )
            return prompt, report

        original_tokens = self._token_counter.count(prompt)
        stages: list[str] = []
        text = prompt

        text, stage = self._whitespace_reduce(text)
        if stage:
            stages.append(stage)

        text, stage = self._shorten_labels(text)
        if stage:
            stages.append(stage)

        text, stage = self._compress_structs(text)
        if stage:
            stages.append(stage)

        if not self._structural_only:
            text, stage = self._compress_system_prompt(text)
            if stage:
                stages.append(stage)

        text, stage = self._enforce_budget(text)
        if stage:
            stages.append(stage)

        final_tokens = self._token_counter.count(text)
        ratio = final_tokens / original_tokens if original_tokens > 0 else 1.0

        return text, MinificationReport(
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            ratio=ratio,
            stages_applied=tuple(stages),
        )

    def _whitespace_reduce(self, text: str) -> tuple[str, str | None]:
        original = text
        text = WHITESPACE_PATTERN.sub("\n\n", text)
        text = TRAILING_SPACE_PATTERN.sub("", text)
        text = text.strip()
        if text != original:
            return text, "whitespace"
        return text, None

    def _shorten_labels(self, text: str) -> tuple[str, str | None]:
        original = text
        text = FILE_LABEL_PATTERN.sub(r"# \1", text)
        if text != original:
            return text, "labels"
        return text, None

    def _compress_structs(self, text: str) -> tuple[str, str | None]:
        original = text

        def _try_compact(match: re.Match) -> str:
            block = match.group(1)
            try:
                parsed = json.loads(block)
                return json.dumps(parsed, separators=(",", ":"))
            except (json.JSONDecodeError, ValueError):
                return match.group(0)

        text = JSON_PATTERN.sub(_try_compact, text)
        if text != original:
            return text, "structs"
        return text, None

    def _compress_system_prompt(self, text: str) -> tuple[str, str | None]:
        original = text

        known_verbosisms = [
            (r"(?i)You are an AI assistant\.?\s*", "#SYSTEM: assistant. "),
            (r"(?i)You are a helpful assistant\.?\s*", "#SYSTEM: helpful assistant. "),
            (r"(?i)You must follow these instructions:\s*", "#INSTRUCT: "),
            (r"(?i)Please analyze the following code\s*", "#ANALYZE: "),
        ]
        for pattern, replacement in known_verbosisms:
            text = re.sub(pattern, replacement, text, count=1)

        if text != original:
            return text, "system_prompt"
        return text, None

    def _enforce_budget(self, text: str) -> tuple[str, str | None]:
        total = self._token_counter.count(text)
        if total <= self._target_tokens:
            return text, None

        sections = text.split("\n\n", maxsplit=1)
        if self._preserve_user_message and len(sections) > 1:
            user_part = sections[-1]
            rest = "\n\n".join(sections[:-1])
            rest_tokens = self._token_counter.count(rest)
            budget = self._target_tokens
            if rest_tokens > budget:
                rest = self._token_counter.truncate(rest, budget)
            result = f"{rest}\n\n{user_part}"
        else:
            result = self._token_counter.truncate(text, self._target_tokens)

        final_tokens = self._token_counter.count(result)
        if final_tokens < total:
            return result, "budget"
        return text, None
