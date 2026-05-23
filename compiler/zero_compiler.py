from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ZERO_EXT = ".zero"


async def get_ast_skeleton(path: Path, zerolang_path: str = "zerolang") -> str:
    """
    Invoke zerolang on the requested file to get its AST structure.
    If zerolang is not available, falls back to a basic language-specific skeleton.
    """
    if shutil.which(zerolang_path):
        try:
            process = await asyncio.create_subprocess_exec(
                zerolang_path,
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error: zerolang failed with code {process.returncode}: {stderr.decode('utf-8')}"
        except Exception as e:
            return f"Error: Failed to execute zerolang: {e}"

    # Fallback logic for when zerolang is missing
    return _generate_fallback_skeleton(path)


def _generate_fallback_skeleton(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".py":
        return _generate_python_skeleton(path)
    # Generic fallback
    return f"(AST Skeleton for {path.name} - fallback)"


def _generate_python_skeleton(path: Path) -> str:
    try:
        import ast

        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        skeleton = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                skeleton.append(f"def {node.name}({', '.join(args)}): ...")
            elif isinstance(node, ast.ClassDef):
                skeleton.append(f"class {node.name}: ...")
        return "\n".join(skeleton) or "(Empty Python AST)"
    except Exception as e:
        return f"(Python AST generation failed: {e})"


async def check_proposed_change(change_content: str, zerolang_path: str = "zerolang") -> tuple[bool, str]:
    """
    Run zerolang --check on a proposed change.
    """
    if not shutil.which(zerolang_path):
        return True, "zerolang not found, skipping check"

    try:
        # Create a temporary file for checking
        temp_file = Path(".zerotmp_check")
        temp_file.write_text(change_content, encoding="utf-8")
        try:
            process = await asyncio.create_subprocess_exec(
                zerolang_path,
                "--check",
                str(temp_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return True, stdout.decode("utf-8")
            else:
                return False, stderr.decode("utf-8")
        finally:
            if temp_file.exists():
                temp_file.unlink()
    except Exception as e:
        return False, f"Error: Failed to run zerolang --check: {e}"


@dataclass(frozen=True)
class ZeroDirective:
    kind: str
    content: str
    token_count: int
    line: int


@dataclass(frozen=True)
class ZeroModule:
    path: str
    directives: list[ZeroDirective]
    raw_token_count: int
    optimized_token_count: int


_TOKEN_PATTERN = re.compile(r"\S+")


def _starts_with_any(text: str, prefixes: tuple[str, ...]) -> bool:
    return any(text.startswith(p) for p in prefixes)


def _count_tokens(text: str) -> int:
    return len(_TOKEN_PATTERN.findall(text))


def parse_zero_file(path: Path) -> ZeroModule:
    raw = path.read_text(encoding="utf-8")
    raw_tokens = _count_tokens(raw)

    directives: list[ZeroDirective] = []
    for i, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue

        kind = "directive"
        content = stripped

        if _starts_with_any(stripped, ("task ", 'task "', "task '")):
            kind = "task"
        elif _starts_with_any(stripped, ("prompt ", 'prompt "', "prompt '")):
            kind = "prompt"
        elif _starts_with_any(stripped, ("agent ", 'agent "', "agent '")):
            kind = "agent"

        directives.append(
            ZeroDirective(
                kind=kind,
                content=content,
                token_count=_count_tokens(content),
                line=i,
            )
        )

    optimized = optimize_module(raw, directives)

    return ZeroModule(
        path=str(path),
        directives=directives,
        raw_token_count=raw_tokens,
        optimized_token_count=_count_tokens(optimized),
    )


def optimize_module(raw: str, directives: list[ZeroDirective]) -> str:
    lines = raw.splitlines()
    optimized: list[str] = []

    for line in lines:
        commentary_patterns = [
            r"^\s*//",
            r"^\s*#",
            r"(?i)basically\s",
            r"(?i)essentially\s",
            r"(?i)simply\s",
            r"(?i)in other words",
            r"(?i)you need to",
            r"(?i)please\s",
        ]
        is_commentary = False
        for pat in commentary_patterns:
            if re.search(pat, line):
                is_commentary = True
                break

        if is_commentary:
            continue

        optimized.append(line)

    return "\n".join(optimized)


def estimate_token_reduction(module: ZeroModule) -> dict[str, Any]:
    from telemetry.metrics import calculate_sdr

    if module.raw_token_count == 0:
        return {"savings_pct": 0, "savings_tokens": 0, "sdr": 0.0}

    metrics = calculate_sdr(module.raw_token_count, module.optimized_token_count)
    savings = metrics.raw_tokens - metrics.ast_tokens
    pct = round(metrics.sdr * 100, 1)

    return {
        "raw_tokens": metrics.raw_tokens,
        "optimized_tokens": metrics.ast_tokens,
        "savings_tokens": savings,
        "savings_pct": pct,
        "sdr": metrics.sdr,
    }


def compile_zero(path: Path) -> dict[str, Any]:
    module = parse_zero_file(path)
    reduction = estimate_token_reduction(module)

    return {
        "status": "ok",
        "path": module.path,
        "directives": len(module.directives),
        "raw_token_count": module.raw_token_count,
        "optimized_token_count": module.optimized_token_count,
        "savings_tokens": reduction["savings_tokens"],
        "savings_pct": reduction["savings_pct"],
        "can_optimize": reduction["savings_tokens"] > 0,
    }
