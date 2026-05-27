from __future__ import annotations

from compiler import parse_structured_diagnostics
from compiler.models import DiagnosticSeverity


def test_parse_structured_diagnostics_handles_json_and_malformed_lines() -> None:
    raw = "\n".join(
        [
            '{"code":"E1","message":"bad token","severity":"error","span":{"path":"main.py","line":2,"column":7}}',
            "not-json-line",
        ]
    )

    diagnostics = parse_structured_diagnostics(raw)

    assert len(diagnostics) == 2
    assert diagnostics[0].code == "E1"
    assert diagnostics[0].severity is DiagnosticSeverity.ERROR
    assert diagnostics[1].code == "MALFORMED_DIAGNOSTIC"
