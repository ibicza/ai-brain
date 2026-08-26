"""Content-addressed source snapshots and evidence extraction."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json
from ai_brain.stage2.facts.models import EvidenceLocationKind
from ai_brain.stage2.facts.version import MAX_SOURCE_BYTES


class SourceIntegrityError(ValueError):
    pass


class ContentAddressedSourceStore:
    def __init__(self, root: Path, *, max_source_bytes: int = MAX_SOURCE_BYTES) -> None:
        self.root = root.resolve()
        self.max_source_bytes = max_source_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes) -> str:
        if not isinstance(content, bytes):
            raise TypeError("source snapshot must be bytes")
        if len(content) > self.max_source_bytes:
            raise ValueError("source snapshot exceeds configured limit")
        digest = bytes_hash(content)
        path = self.path_for(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise SourceIntegrityError(
                    "existing source blob does not match its hash"
                )
            return digest
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(content)
        if bytes_hash(temporary.read_bytes()) != digest:
            temporary.unlink(missing_ok=True)
            raise SourceIntegrityError("source snapshot changed while storing")
        os.replace(temporary, path)
        return digest

    def read(self, digest: str) -> bytes:
        path = self.path_for(digest)
        if not path.is_file():
            raise SourceIntegrityError(f"missing source blob: {digest}")
        content = path.read_bytes()
        if bytes_hash(content) != digest:
            raise SourceIntegrityError(f"changed source blob: {digest}")
        return content

    def verify(self, digest: str) -> None:
        self.read(digest)

    def path_for(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid SHA-256 digest")
        path = (self.root / "sha256" / digest[:2] / digest[2:]).resolve()
        if self.root not in path.parents:
            raise ValueError("source blob path escaped the store")
        return path

    def manifest(self) -> list[dict[str, Any]]:
        rows = []
        base = self.root / "sha256"
        if not base.exists():
            return rows
        for path in sorted(item for item in base.glob("*/*") if item.is_file()):
            digest = f"{path.parent.name}{path.name}"
            self.verify(digest)
            rows.append({"sha256": digest, "size": path.stat().st_size})
        return rows


def extract_evidence(
    content: bytes,
    location_kind: EvidenceLocationKind | str,
    location: dict[str, Any],
    *,
    media_type: str,
) -> bytes:
    kind = EvidenceLocationKind(location_kind)
    if kind == EvidenceLocationKind.BYTE_SPAN:
        start, end = _span(location, len(content))
        return content[start:end]
    if kind == EvidenceLocationKind.CHAR_SPAN:
        try:
            text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise SourceIntegrityError(
                "character evidence requires valid UTF-8"
            ) from error
        start, end = _span(location, len(text))
        return text[start:end].encode("utf-8")
    if kind == EvidenceLocationKind.JSON_POINTER:
        if "json" not in media_type.lower():
            raise ValueError("JSON pointer requires a JSON source")
        try:
            document = json.loads(content.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceIntegrityError("invalid JSON source snapshot") from error
        pointer = location.get("pointer")
        if not isinstance(pointer, str):
            raise ValueError("JSON pointer location requires pointer")
        selected = resolve_json_pointer(document, pointer)
        return canonical_json(selected).encode("utf-8")
    raise ValueError(f"unsupported evidence location kind: {kind}")


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("malformed JSON pointer")
    current = document
    for raw in pointer[1:].split("/"):
        token = _decode_pointer_token(raw)
        if isinstance(current, dict):
            if token not in current:
                raise ValueError("JSON pointer does not exist")
            current = current[token]
        elif isinstance(current, list):
            if (
                token == "-"
                or not token.isdigit()
                or (token.startswith("0") and token != "0")
            ):
                raise ValueError("invalid JSON array pointer")
            index = int(token)
            if index >= len(current):
                raise ValueError("JSON pointer does not exist")
            current = current[index]
        else:
            raise TypeError("JSON pointer traverses a scalar")
    return current


def _decode_pointer_token(token: str) -> str:
    result = []
    index = 0
    while index < len(token):
        if token[index] != "~":
            result.append(token[index])
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in "01":
            raise ValueError("malformed JSON pointer escape")
        result.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _span(location: dict[str, Any], length: int) -> tuple[int, int]:
    start = location.get("start")
    end = location.get("end")
    if isinstance(start, bool) or isinstance(end, bool):
        raise TypeError("span bounds must be integers")
    if not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("span requires integer start and end")
    if start < 0 or end <= start or end > length:
        raise ValueError("evidence span is outside the source snapshot")
    return start, end
