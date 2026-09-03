"""Enforced file-read audit for oracle-free Java production runs."""

from __future__ import annotations

import builtins
import io
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash

_FORBIDDEN_PARTS = frozenset({"oracle", "golden", "goldens", "evaluation"})


@dataclass(frozen=True)
class JavaProductionFileAuditReport:
    read_count: int
    unique_read_paths: tuple[str, ...]
    forbidden_read_count: int
    blocked_paths: tuple[str, ...]
    report_hash: str


class EnforcedJavaProductionFileAudit:
    """Record reads and reject any path bearing evaluation authority markers."""

    def __init__(self) -> None:
        self._reads: list[str] = []
        self._blocked: list[str] = []
        self._builtins_open = None
        self._io_open = None

    def __enter__(self):
        self._builtins_open = builtins.open
        self._io_open = io.open
        builtins.open = self._guard(self._builtins_open)
        io.open = self._guard(self._io_open)
        return self

    def __exit__(self, *_args):
        builtins.open = self._builtins_open
        io.open = self._io_open

    def _guard(self, original):
        def guarded(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, bytes, Path)) and "r" in str(mode):
                normalized = Path(file).resolve(strict=False).as_posix()
                parts = {part.casefold() for part in Path(normalized).parts}
                if parts & _FORBIDDEN_PARTS:
                    self._blocked.append(normalized)
                    raise PermissionError(
                        "oracle/golden/evaluation file read is forbidden in production"
                    )
                self._reads.append(normalized)
            return original(file, mode, *args, **kwargs)

        return guarded

    def report(self) -> JavaProductionFileAuditReport:
        body = {
            "read_count": len(self._reads),
            "unique_read_paths": tuple(sorted(set(self._reads))),
            "forbidden_read_count": len(self._blocked),
            "blocked_paths": tuple(self._blocked),
        }
        return JavaProductionFileAuditReport(**body, report_hash=content_hash(body))
