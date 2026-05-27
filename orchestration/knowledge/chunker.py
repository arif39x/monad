from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    start_line: int
    end_line: int
    language: str = "unknown"


class CodeAwareChunker:
    def __init__(
        self,
        *,
        max_chunk_tokens: int = 200,
        overlap_tokens: int = 50,
    ) -> None:
        self._max_chunk_tokens = max_chunk_tokens
        self._overlap_tokens = overlap_tokens

    def chunk(self, content: str, language: str = "unknown") -> list[Chunk]:
        if not content.strip():
            return []

        if language == "python":
            chunks = self._chunk_python_ast(content)
            if chunks:
                return chunks

        return self._chunk_fallback(content)

    def _chunk_python_ast(self, content: str) -> list[Chunk]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        chunks: list[Chunk] = []
        lines = content.splitlines(keepends=False)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno
                end_line = getattr(node, "end_lineno", None) or start_line
                text = "\n".join(lines[start_line - 1 : end_line])
                chunks.append(Chunk(
                    text=text,
                    start_line=start_line,
                    end_line=end_line,
                    language="python",
                ))

        if not chunks:
            return self._chunk_fallback(content)

        return chunks

    def _chunk_fallback(self, content: str) -> list[Chunk]:
        lines = content.splitlines(keepends=False)
        chunks: list[Chunk] = []
        chunk_size = max(self._max_chunk_tokens, 1)
        overlap = min(self._overlap_tokens, chunk_size // 2)
        step = max(chunk_size - overlap, 1)

        i = 0
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            text = "\n".join(lines[i:end])
            chunks.append(Chunk(
                text=text,
                start_line=i + 1,
                end_line=end,
                language="unknown",
            ))
            i += step

        return chunks
