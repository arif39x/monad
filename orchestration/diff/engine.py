from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class FileSnapshot:
    path: Path
    hash: str
    mtime: float
    lines: list[str]


@dataclass
class DiffOperation:
    kind: Literal["insert", "delete", "replace"]
    start_line: int
    count: int
    text: str = ""


@dataclass
class ContentDelta:
    path: Path
    snapshot_hash: str
    operations: list[DiffOperation] = field(default_factory=list)
    is_new: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.operations)


class ContextDiffEngine:
    def __init__(
        self,
        *,
        max_snapshots: int = 100,
        enabled: bool = True,
    ) -> None:
        self._snapshots: dict[Path, FileSnapshot] = {}
        self._max_snapshots = max_snapshots
        self._enabled = enabled

    async def compute_delta(self, path: Path) -> ContentDelta:
        if not self._enabled:
            return self._full_content_delta(path)

        current = self._read_snapshot(path)
        previous = self._snapshots.get(path)

        if len(self._snapshots) >= self._max_snapshots and previous is None:
            self._evict_lru()

        if previous is None:
            self._snapshots[path] = current
            return ContentDelta(
                path=path,
                snapshot_hash=current.hash,
                operations=[],
                is_new=True,
            )

        if previous.hash == current.hash:
            return ContentDelta(
                path=path,
                snapshot_hash=current.hash,
                operations=[],
            )

        diff = self._compute_diff(previous.lines, current.lines)
        self._snapshots[path] = current
        return ContentDelta(
            path=path,
            snapshot_hash=current.hash,
            operations=diff,
        )

    def render_delta(self, delta: ContentDelta) -> str:
        if delta.is_new:
            snapshot = self._snapshots.get(delta.path)
            if snapshot:
                return f"# {delta.path.name}\n" + "\n".join(snapshot.lines)
            return f"# {delta.path.name} (new file)"

        if not delta.has_changes:
            return f"# {delta.path.name} (unchanged, hash: {delta.snapshot_hash[:8]})"

        lines = [f"# {delta.path.name} (modified)"]
        for op in delta.operations:
            if op.text:
                lines.append(op.text)
        return "\n".join(lines)

    def get_snapshot(self, path: Path) -> FileSnapshot | None:
        return self._snapshots.get(path)

    def clear(self) -> None:
        self._snapshots.clear()

    @property
    def stats(self) -> dict:
        return {
            "num_snapshots": len(self._snapshots),
            "max_snapshots": self._max_snapshots,
            "enabled": self._enabled,
        }

    def _read_snapshot(self, path: Path) -> FileSnapshot:
        resolved = path.resolve()
        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=False)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        mtime = resolved.stat().st_mtime
        return FileSnapshot(path=resolved, hash=content_hash, mtime=mtime, lines=lines)

    def _compute_diff(
        self,
        old_lines: list[str],
        new_lines: list[str],
    ) -> list[DiffOperation]:
        operations: list[DiffOperation] = []
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "replace":
                old_text = "\n".join(old_lines[i1:i2])
                new_text = "\n".join(new_lines[j1:j2])
                operations.append(DiffOperation(
                    kind="replace",
                    start_line=j1 + 1,
                    count=j2 - j1,
                    text=self._format_diff_snippet(old_text, new_text, j1 + 1),
                ))
            elif tag == "delete":
                text = "\n".join(old_lines[i1:i2])
                operations.append(DiffOperation(
                    kind="delete",
                    start_line=i1 + 1,
                    count=i2 - i1,
                    text=f"-{text}" if text else "-",
                ))
            elif tag == "insert":
                text = "\n".join(new_lines[j1:j2])
                operations.append(DiffOperation(
                    kind="insert",
                    start_line=j1 + 1,
                    count=j2 - j1,
                    text=f"+{text}" if text else "+",
                ))

        return operations

    def _format_diff_snippet(self, old_text: str, new_text: str, line_num: int) -> str:
        return f"@@ -{line_num} +{line_num} @@\n-{old_text}\n+{new_text}"

    def _full_content_delta(self, path: Path) -> ContentDelta:
        snapshot = self._read_snapshot(path)
        return ContentDelta(
            path=path,
            snapshot_hash=snapshot.hash,
            operations=[],
            is_new=True,
        )

    def _evict_lru(self) -> None:
        if not self._snapshots:
            return
        oldest = min(self._snapshots.keys(), key=lambda p: self._snapshots[p].mtime)
        del self._snapshots[oldest]
