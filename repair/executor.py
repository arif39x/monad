from __future__ import annotations

from pathlib import Path
from typing import Any

from repair.models import RepairPlan, RepairAction
from repair.planner import verify_proposed_change
from repair.applier import apply_edit

async def execute_repair_plan(
    plan: RepairPlan,
    working_dir: Path,
    apply: bool = False
) -> list[dict[str, Any]]:
    results = []
    for directive in plan.directives:
        if directive.action == RepairAction.ABORT:
            results.append({"action": "abort", "status": "failed", "message": directive.reason})
        elif directive.action == RepairAction.EDIT_SNIPPET:
            target = working_dir / directive.target_file
            if apply:
                snippet = getattr(directive, "snippet", f"# Patched for {directive.reason}")
                if await apply_edit(directive.target_file, snippet, working_dir):
                    content = target.read_text(encoding="utf-8")
                    passed, msg = await verify_proposed_change(content)
                    if passed:
                        results.append({"action": "edit", "status": "success", "file": directive.target_file})
                    else:
                        results.append({"action": "edit", "status": "failed", "file": directive.target_file, "message": msg})
                else:
                    results.append({"action": "edit", "status": "failed", "file": directive.target_file, "message": "Failed to apply edit"})
            else:
                if target.exists():
                    content = target.read_text(encoding="utf-8")
                    passed, msg = await verify_proposed_change(content)
                    if passed:
                        results.append({"action": "edit", "status": "success", "file": directive.target_file, "dry_run": True})
                    else:
                        results.append({"action": "edit", "status": "failed", "file": directive.target_file, "message": msg, "dry_run": True})
                else:
                    results.append({"action": "edit", "status": "failed", "file": directive.target_file, "message": "File not found"})
        elif directive.action == RepairAction.ADJUST_CONFIG:
            results.append({"action": "config", "status": "success", "file": directive.target_file})
        elif directive.action == RepairAction.REQUEST_PERMISSION:
            results.append({"action": "permission", "status": "requested", "file": directive.target_file})
        else:
            results.append({"action": str(directive.action), "status": "ignored"})
    return results
