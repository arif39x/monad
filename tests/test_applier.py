from __future__ import annotations

import asyncio
from pathlib import Path

from repair.applier import apply_edit


def test_apply_edit_new_content(tmp_path: Path) -> None:
    target = tmp_path / "test.py"
    target.write_text("original\n")
    result = asyncio.run(apply_edit(Path("test.py"), "new_line()", tmp_path))
    assert result is True
    assert "new_line()" in target.read_text()


def test_apply_edit_skips_if_already_present(tmp_path: Path) -> None:
    target = tmp_path / "test.py"
    target.write_text("existing_content\n")
    result = asyncio.run(apply_edit(Path("test.py"), "existing_content", tmp_path))
    assert result is True
    assert target.read_text() == "existing_content\n"


def test_apply_edit_file_not_found(tmp_path: Path) -> None:
    result = asyncio.run(apply_edit(Path("nonexistent.py"), "content", tmp_path))
    assert result is False


def test_apply_edit_appends_at_end(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("line1\n")
    asyncio.run(apply_edit(Path("module.py"), "line2", tmp_path))
    content = target.read_text()
    assert content.endswith("line2\n")
