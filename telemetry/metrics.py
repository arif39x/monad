from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class Timing:
    operation: str
    duration_ms: int


@dataclass(frozen=True)
class SemanticMetrics:
    raw_tokens: int
    ast_tokens: int
    sdr: float


def calculate_sdr(raw_token_count: int, ast_token_count: int) -> SemanticMetrics:
    """
    SDR = (Raw_Token_Count - AST_Token_Count) / Raw_Token_Count
    """
    if raw_token_count == 0:
        sdr = 0.0
    else:
        sdr = (raw_token_count - ast_token_count) / raw_token_count

    return SemanticMetrics(
        raw_tokens=raw_token_count,
        ast_tokens=ast_token_count,
        sdr=round(sdr, 4),
    )


@contextmanager
def measure(operation: str):
    start = perf_counter()
    try:
        yield
    finally:
        duration_ms = int((perf_counter() - start) * 1000)
        _ = Timing(operation=operation, duration_ms=duration_ms)
