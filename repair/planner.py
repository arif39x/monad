from __future__ import annotations

from typing import TYPE_CHECKING

from compiler.models import CompilerDiagnostic
from diagnostics import FailureClass, classify_diagnostic
from orchestration.config import RepairSettings
from repair.models import RepairAction, RepairDirective, RepairPlan

if TYPE_CHECKING:
    from pathlib import Path


async def verify_proposed_change(
    change_content: str,
    zerolang_path: str | None = None,
) -> tuple[bool, str]:
    """
    Zero-Repair Flow:
    1. Run zerolang --check <proposed_change>.
    2. If Pass: Return (True, success_msg).
    3. If Fail: Return (False, diagnostic_error).
    """
    from compiler.zero_compiler import check_proposed_change

    passed, message = await check_proposed_change(change_content, zerolang_path)
    return passed, message


def build_repair_plan(
    diagnostics: list[CompilerDiagnostic],
    *,
    attempt: int,
    settings: RepairSettings,
) -> RepairPlan:
    if attempt > settings.max_attempts:
        return RepairPlan(
            attempt=attempt,
            directives=[
                RepairDirective(
                    action=RepairAction.ABORT,
                    target_file="",
                    reason="Maximum repair attempts exceeded",
                    instructions="Escalate to human reviewer.",
                    failure_class=FailureClass.UNKNOWN,
                )
            ],
            requires_recompile=False,
        )

    directives: list[RepairDirective] = []

    for diagnostic in diagnostics:
        classified = classify_diagnostic(diagnostic)
        directives.append(_directive_for(classified.failure_class, diagnostic))

    requires_recompile = any(
        directive.action in {RepairAction.EDIT_SNIPPET, RepairAction.ADJUST_CONFIG}
        for directive in directives
    )

    return RepairPlan(
        attempt=attempt,
        directives=directives,
        requires_recompile=requires_recompile,
    )


def _directive_for(failure_class: FailureClass, diagnostic: CompilerDiagnostic) -> RepairDirective:
    target_file = diagnostic.span.path

    if failure_class in {FailureClass.SYNTAX, FailureClass.TYPE}:
        return RepairDirective(
            action=RepairAction.EDIT_SNIPPET,
            target_file=target_file,
            reason=diagnostic.message,
            instructions=(
                "Patch only the smallest affected region around the reported span "
                "and preserve all unrelated code."
            ),
            failure_class=failure_class,
        )

    if failure_class in {FailureClass.CAPABILITY, FailureClass.SANDBOX}:
        return RepairDirective(
            action=RepairAction.REQUEST_PERMISSION,
            target_file=target_file,
            reason=diagnostic.message,
            instructions="Validate policy and request explicit capability approval.",
            failure_class=failure_class,
        )

    if failure_class is FailureClass.TIMEOUT:
        return RepairDirective(
            action=RepairAction.ADJUST_CONFIG,
            target_file="configs/elyon.toml",
            reason=diagnostic.message,
            instructions="Tune timeout values conservatively and retry.",
            failure_class=failure_class,
        )

    return RepairDirective(
        action=RepairAction.ABORT,
        target_file=target_file,
        reason=diagnostic.message,
        instructions="Classification is unknown; do not apply speculative patch.",
        failure_class=failure_class,
    )
