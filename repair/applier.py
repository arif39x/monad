from __future__ import annotations

from pathlib import Path


async def apply_edit(file_path: Path, snippet: str, working_dir: Path) -> bool:
    target = working_dir / file_path
    if not target.exists():
        return False
    current = target.read_text(encoding="utf-8")
    if snippet in current:
        return True
    target.write_text(current.rstrip("\n") + "\n" + snippet + "\n")
    return True
