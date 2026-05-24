from __future__ import annotations

import logging

from telemetry.metrics import Timing, SemanticMetrics, calculate_sdr, measure


def test_calculate_sdr_zero_raw() -> None:
    m = calculate_sdr(0, 0)
    assert m.raw_tokens == 0
    assert m.ast_tokens == 0
    assert m.sdr == 0.0


def test_calculate_sdr_full_savings() -> None:
    m = calculate_sdr(100, 0)
    assert m.sdr == 1.0


def test_calculate_sdr_half_savings() -> None:
    m = calculate_sdr(100, 50)
    assert m.sdr == 0.5


def test_calculate_sdr_no_savings() -> None:
    m = calculate_sdr(100, 100)
    assert m.sdr == 0.0


def test_calculate_sdr_rounding() -> None:
    m = calculate_sdr(3, 1)
    assert m.sdr == round((3 - 1) / 3, 4)


def test_measure_emits_timing() -> None:
    with measure("test-op") as t:
        t.raw_tokens = 100
        t.ast_tokens = 30

    assert t.operation == "test-op"
    assert t.raw_tokens == 100
    assert t.ast_tokens == 30
    assert t.emitted is True
    assert t.elapsed_ms >= 0


def test_measure_with_logger() -> None:
    records: list[logging.LogRecord] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("test-measure")
    logger.addHandler(CaptureHandler())
    logger.setLevel(logging.INFO)

    with measure("logged-op", logger=logger) as t:
        t.raw_tokens = 200
        t.ast_tokens = 50

    assert len(records) == 1
    assert records[0].msg == "timing"
    assert records[0].operation == "logged-op"
    assert records[0].raw_tokens == 200
    assert records[0].ast_tokens == 50
    assert records[0].sdr == 0.75


def test_timing_defaults() -> None:
    t = Timing(operation="defaults")
    assert t.raw_tokens == 0
    assert t.ast_tokens == 0
    assert t.elapsed_ms == 0.0
    assert t.emitted is False


def test_semantic_metrics_frozen() -> None:
    m = SemanticMetrics(raw_tokens=10, ast_tokens=5, sdr=0.5)
    import pytest
    with pytest.raises(AttributeError):
        m.raw_tokens = 20
