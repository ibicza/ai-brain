"""Content-addressed persistence for non-authoritative chemistry results."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json, content_hash


class ChemistryResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, result: dict[str, Any]) -> Path:
        digest = result.get("result_hash")
        body = {key: value for key, value in result.items() if key != "result_hash"}
        if not isinstance(digest, str) or content_hash(body) != digest:
            raise ValueError("invalid chemistry result artifact")
        path = self._path(digest)
        payload = (canonical_json(result) + "\n").encode("utf-8")
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("stored chemistry result hash collision")
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)
        return path

    def load(self, digest: str) -> dict[str, Any]:
        result = json.loads(self._path(digest).read_text(encoding="utf-8"))
        body = {key: value for key, value in result.items() if key != "result_hash"}
        if result.get("result_hash") != digest or content_hash(body) != digest:
            raise ValueError("stored chemistry result failed verification")
        return result

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid chemistry result hash")
        path = (self.root / digest[:2] / f"{digest[2:]}.json").resolve()
        if self.root not in path.parents:
            raise ValueError("chemistry result path escaped store")
        return path
