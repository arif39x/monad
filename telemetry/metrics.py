from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class Timing:
    operation: str
    raw_tokens: int = 0
    ast_tokens: int = 0
    elapsed_ms: float = 0.0
    emitted: bool = False


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
def measure(operation: str, logger: logging.Logger | None = None):
    start = time.monotonic()
    timing = Timing(operation=operation)
    try:
        yield timing
    finally:
        timing.elapsed_ms = (time.monotonic() - start) * 1000
        timing.emitted = True
        if logger:
            logger.info("timing", extra={
                "operation": timing.operation,
                "elapsed_ms": timing.elapsed_ms,
                "raw_tokens": timing.raw_tokens,
                "ast_tokens": timing.ast_tokens,
                "sdr": calculate_sdr(timing.raw_tokens, timing.ast_tokens).sdr,
            })
