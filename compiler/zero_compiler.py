from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ZERO_EXT = ".zero"
ZEROLANG_EXT = ".0"

ZERO_BINARY = "zero"


async def get_ast_skeleton(path: Path, zerolang_path: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """
    For zerolang (.0) files: invoke `zero parse --json` to get structured parse data.
    For other files: falls back to a basic language-specific skeleton.
    """
    ext = path.suffix.lower()
    if ext == ZEROLANG_EXT:
        binary = _resolve_zero_binary(zerolang_path)
        if binary:
            return await _parse_zerolang_file(path, binary)
        return "(zerolang compiler not found)", []

    return _generate_fallback_skeleton(path)


def _resolve_zero_binary(zerolang_path: str | None) -> str | None:
    if zerolang_path:
        candidate = shutil.which(zerolang_path) or zerolang_path
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    local = Path(".zero/bin/zero")
    if local.is_file() and os.access(local, os.X_OK):
        return str(local.resolve())
    return shutil.which(ZERO_BINARY)


async def _parse_zerolang_file(path: Path, binary: str) -> tuple[str, list[dict[str, Any]]]:
    try:
        process = await asyncio.create_subprocess_exec(
            binary, "parse", "--json", str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            return f"Error: zero parse failed ({process.returncode}): {stderr.decode('utf-8')}", []
        data = json.loads(stdout.decode("utf-8"))
    except Exception as e:
        return f"Error: zero parse failed: {e}", []

    skeleton_lines = [f"// {data.get('sourceFile', path.name)}"]
    knowledge: list[dict[str, Any]] = []

    for fn in data.get("functions", []):
        fn_name = fn.get("name", "?")
        return_type = fn.get("returnType", "Void")
        param_count = fn.get("paramCount", 0)
        body_kinds = ", ".join(fn.get("bodyKinds", []))
        skeleton_lines.append(f"fn {fn_name} {return_type} # params={param_count}, body={{{body_kinds}}}")
        knowledge.append({
            "symbol": fn_name,
            "content": f"function {fn_name}: {return_type}, {param_count} params",
            "kind": "zerolang-function",
            "line": fn.get("line", 0),
        })

    root = data.get("root", {})
    skeleton_lines.insert(0, f"// module: {root.get('functionCount', 0)} functions, "
                             f"{root.get('shapeCount', 0)} shapes, "
                             f"{root.get('enumCount', 0)} enums")

    return "\n".join(skeleton_lines), knowledge


def _generate_fallback_skeleton(path: Path) -> tuple[str, list[dict[str, Any]]]:
    ext = path.suffix.lower()
    if ext == ".py":
        return _generate_python_skeleton(path)
    # Generic fallback
    try:
        return path.read_text(encoding="utf-8"), []
    except Exception as e:
        return f"(Fallback failed: {e})", []


def _generate_python_skeleton(path: Path) -> tuple[str, list[dict[str, Any]]]:
    try:
        import ast

        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        skeleton = []
        knowledge = []

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                skeleton.append(f"def {node.name}({', '.join(args)}): ...")
                docstring = ast.get_docstring(node)
                if docstring:
                    knowledge.append({
                        "symbol": node.name,
                        "content": docstring,
                        "kind": "docstring",
                        "line": node.lineno
                    })
            elif isinstance(node, ast.ClassDef):
                skeleton.append(f"class {node.name}: ...")
                docstring = ast.get_docstring(node)
                if docstring:
                    knowledge.append({
                        "symbol": node.name,
                        "content": docstring,
                        "kind": "docstring",
                        "line": node.lineno
                    })
        return "\n".join(skeleton) or "(Empty Python AST)", knowledge
    except Exception as e:
        return f"(Python AST generation failed: {e})", []


async def check_proposed_change(change_content: str, zerolang_path: str | None = None) -> tuple[bool, str]:
    """
    Run `zero check --json` on proposed zerolang code.
    """
    binary = _resolve_zero_binary(zerolang_path)
    if not binary:
        return True, f"{ZERO_BINARY} not found, skipping check"

    try:
        temp_dir = Path(".zerotmp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / ".zerotmp_check.0"
        temp_file.write_text(change_content, encoding="utf-8")
        try:
            process = await asyncio.create_subprocess_exec(
                binary, "check", "--json", str(temp_file),
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
            if temp_dir.exists():
                try:
                    temp_dir.rmdir()
                except OSError:
                    pass
    except Exception as e:
        return False, f"Error: Failed to run {ZERO_BINARY} check: {e}"


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
    import logging
    from telemetry.metrics import measure
    logger = logging.getLogger(__name__)

    with measure("compile_zero", logger) as timing:
        module = parse_zero_file(path)
        reduction = estimate_token_reduction(module)
        timing.raw_tokens = module.raw_token_count
        timing.ast_tokens = module.optimized_token_count

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
