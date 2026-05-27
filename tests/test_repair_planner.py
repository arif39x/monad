from __future__ import annotations

from compiler.models import CompilerDiagnostic, DiagnosticSeverity, SourceSpan
from orchestration.config import RepairSettings
from repair import RepairAction, build_repair_plan


def test_repair_planner_uses_minimal_edit_for_syntax_errors() -> None:
    diagnostics = [
        CompilerDiagnostic(
            code="SYNTAX_ERROR",
            message="parse failure",
            severity=DiagnosticSeverity.ERROR,
            span=SourceSpan(path="src/main.py", line=4, column=2),
        )
    ]

    settings = RepairSettings(
        max_attempts=3,
        verify_after_repair=True,
        allowed_extensions=[".py"],
    )

    plan = build_repair_plan(diagnostics, attempt=1, settings=settings)

    assert plan.requires_recompile is True
    assert plan.directives[0].action is RepairAction.EDIT_SNIPPET
    assert plan.directives[0].target_file == "src/main.py"


def test_repair_planner_aborts_after_max_attempts() -> None:
    diagnostics = [
        CompilerDiagnostic(
            code="TYPE_MISMATCH",
            message="type mismatch",
            severity=DiagnosticSeverity.ERROR,
            span=SourceSpan(path="src/lib.rs", line=10, column=5),
        )
    ]

    settings = RepairSettings(
        max_attempts=2,
        verify_after_repair=True,
        allowed_extensions=[".rs"],
    )

    plan = build_repair_plan(diagnostics, attempt=3, settings=settings)

    assert plan.requires_recompile is False
    assert plan.directives[0].action is RepairAction.ABORT
