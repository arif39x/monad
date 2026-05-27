from __future__ import annotations


class TokenCounter:
    def __init__(self, model: str = "gpt-4") -> None:
        self._model = model
        self._encoding = None

    def _get_encoding(self):
        if self._encoding is None:
            try:
                import tiktoken
                try:
                    self._encoding = tiktoken.encoding_for_model(self._model)
                except KeyError:
                    self._encoding = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                pass
        return self._encoding

    def count(self, text: str) -> int:
        encoding = self._get_encoding()
        if encoding is not None:
            return len(encoding.encode(text, disallowed_special=()))
        return len(text) // 4

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        encoding = self._get_encoding()
        if encoding is not None:
            tokens = encoding.encode(text, disallowed_special=())
            if len(tokens) <= max_tokens:
                return text
            return encoding.decode(tokens[:max_tokens])
        if len(text) <= max_tokens * 4:
            return text
        return text[: max_tokens * 4]
