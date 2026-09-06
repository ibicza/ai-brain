"""Memory-bounded exact fresh-source leak scan for public evidence trees."""

from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_PACK_ENTRY_CONTRACTS,
    _count_private_roles,
    _decoded_source_payload_count,
    public_path_count,
)

_SOURCE_WINDOW_BYTES = 256
_ANCHOR_BYTES = 16
_ANCHOR_STRIDE = 128


def scan_fresh_source_leaks(vault: Path, public: Path | tuple[Path, ...]) -> dict:
    """Reject exact source bodies, encodings, paths, and 256-byte windows.

    The exact window join uses a disk-backed 16-byte anchor index. Every
    256-byte source window contains an anchor on the frozen 128-byte grid.
    Rolling hashes only select candidates; surrounding bytes are compared
    exactly before a leak counts.
    """

    owns_tracemalloc = not tracemalloc.is_tracing()
    if owns_tracemalloc:
        tracemalloc.start()
    started = time.perf_counter()
    source_jars = tuple(vault.glob("candidates/*/source.jar"))
    scm_archives = tuple(vault.glob("candidates/*/scm.zip"))
    java_files = tuple(
        sorted(
            vault.glob("candidates/*/sources/**/*.java"),
            key=lambda item: item.relative_to(vault).as_posix().encode(),
        )
    )
    legal_files = tuple(
        item for item in vault.glob("candidates/*/legal/**/*") if item.is_file()
    )
    public_roots = public if isinstance(public, tuple) else (public,)
    public_files = tuple(
        sorted(
            {
                item.resolve(strict=True)
                for root in public_roots
                for item in root.rglob("*")
                if item.is_file()
            },
            key=lambda item: str(item).encode(),
        )
    )
    source_jar_identities = _file_identities(source_jars)
    scm_identities = _file_identities(scm_archives)
    java_identities = _file_identities(java_files, minimum_bytes=256)
    legal_identities = _file_identities(legal_files, minimum_bytes=256)
    exact_source_jar = exact_scm = exact_java = encoded = legal = 0
    absolute = 0
    private_roles = 0
    reversible = 0
    for path in public_files:
        raw = path.read_bytes()
        identity = (len(raw), bytes_hash(raw))
        exact_source_jar += int(identity in source_jar_identities)
        exact_scm += int(identity in scm_identities)
        exact_java += int(identity in java_identities)
        encoded += _encoded_source_body_count(raw, path.suffix, java_identities)
        legal += int(identity in legal_identities)
        if path.suffix.casefold() in {".json", ".md", ".txt", ".log"}:
            text = raw.decode("utf-8", errors="ignore")
            try:
                value = json.loads(text) if path.suffix.casefold() == ".json" else text
            except json.JSONDecodeError:
                value = text
            absolute += public_path_count(value)
            private_roles += _count_private_roles(value)
            reversible += _decoded_source_payload_count(value)
    source_window = _source_window_leak_count(java_files, public_files)
    allowed_pack_entries = {
        item.entry_name for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACTS
    }
    pack_roots = {
        path.parent
        for path in public_files
        if path.name == "manifest.json" and (path.parent / "knowledge.jsonl").is_file()
    }
    unknown_pack_entries = sum(
        len({item.name for item in root.iterdir()} - allowed_pack_entries)
        for root in pack_roots
    )
    counts = {
        "exact_source_jar_body_count": exact_source_jar,
        "exact_scm_archive_body_count": exact_scm,
        "complete_extracted_java_file_count": exact_java,
        "exact_256_byte_source_window_count": source_window,
        "base64_or_hex_source_body_count": encoded,
        "local_vault_absolute_path_count": absolute,
        "raw_license_document_body_count": legal,
        "source_excerpt_publication_receipt_count": 0,
        "private_artifact_role_count": private_roles,
        "unknown_public_pack_entry_count": unknown_pack_entries,
        "public_absolute_path_count": absolute,
        "public_reversible_source_payload_count": reversible,
        "public_source_window_count": source_window,
    }
    total = (
        exact_source_jar
        + exact_scm
        + exact_java
        + source_window
        + max(encoded, reversible)
        + absolute
        + legal
        + private_roles
        + unknown_pack_entries
    )
    elapsed = time.perf_counter() - started
    _current_python_bytes, peak_python_bytes = tracemalloc.get_traced_memory()
    if owns_tracemalloc:
        tracemalloc.stop()
    body = {
        "schema_version": 1,
        **counts,
        "fresh_source_leak_count": total,
        "scanned_public_file_count": len(public_files),
        "scanned_java_file_count": len(java_files),
        "leak_scan_seconds": f"{elapsed:.6f}",
        "throughput_public_files_per_second": f"{len(public_files) / elapsed:.6f}",
        "peak_python_bytes": peak_python_bytes,
        "status": "PASS" if not total else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _file_identities(
    paths: tuple[Path, ...], *, minimum_bytes: int = 0
) -> set[tuple[int, str]]:
    result = set()
    for path in paths:
        raw = path.read_bytes()
        if len(raw) >= minimum_bytes:
            result.add((len(raw), bytes_hash(raw)))
    return result


def _encoded_source_body_count(
    raw: bytes, suffix: str, source_identities: set[tuple[int, str]]
) -> int:
    if not source_identities or suffix.casefold() not in {
        ".json",
        ".md",
        ".txt",
        ".log",
    }:
        return 0
    text = raw.decode("utf-8", errors="ignore")
    values = []
    if suffix.casefold() == ".json":
        try:
            pending = [json.loads(text)]
        except json.JSONDecodeError:
            pending = []
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, str):
                values.append(value)
    values.extend(re.findall(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{512,}(?![0-9A-Fa-f])", text))
    values.extend(
        re.findall(
            r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{342,}={0,2}(?![A-Za-z0-9+/=])",
            text,
        )
    )
    for value in values:
        compact = "".join(value.split())
        decoded = []
        if len(compact) >= 512 and len(compact) % 2 == 0:
            try:
                decoded.append(bytes.fromhex(compact))
            except ValueError:
                pass
        if len(compact) >= 344 and len(compact) % 4 == 0:
            try:
                decoded.append(base64.b64decode(compact, validate=True))
            except (ValueError, binascii.Error):
                pass
        if any((len(item), bytes_hash(item)) in source_identities for item in decoded):
            return 1
    return 0


def _source_window_leak_count(
    source_paths: tuple[Path, ...], public_paths: tuple[Path, ...]
) -> int:
    if not source_paths or not public_paths:
        return 0
    with tempfile.TemporaryDirectory(prefix="m336d-window-index-") as temporary:
        database = Path(temporary) / "windows.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute(
                "CREATE TABLE source_anchor "
                "(anchor_bytes BLOB NOT NULL, source_index INTEGER NOT NULL, "
                "source_offset INTEGER NOT NULL)"
            )
            for source_index, path in enumerate(source_paths):
                _insert_source_anchors(
                    connection, path.read_bytes(), source_index=source_index
                )
            connection.execute(
                "CREATE INDEX source_anchor_bytes ON source_anchor(anchor_bytes)"
            )
            anchor_blobs = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT anchor_bytes FROM source_anchor"
                )
            }
            anchor_values = np.frombuffer(b"".join(anchor_blobs), dtype="<u8").reshape(
                (-1, 2)
            )
            anchor_filters = _build_anchor_filters(anchor_values)
            source_cache: dict[int, bytes] = {}
            leaked_public_files = 0
            for path in public_paths:
                public_raw = path.read_bytes()
                if len(public_raw) < 256:
                    continue
                leaked = False
                for public_offset, anchor_bytes in _matching_anchor_offsets(
                    public_raw, anchor_filters
                ):
                    for source_index, source_offset in connection.execute(
                        "SELECT source_index, source_offset FROM source_anchor "
                        "WHERE anchor_bytes = ?",
                        (anchor_bytes,),
                    ):
                        source_raw = source_cache.get(source_index)
                        if source_raw is None:
                            source_raw = source_paths[source_index].read_bytes()
                            source_cache.clear()
                            source_cache[source_index] = source_raw
                        if public_raw[
                            public_offset : public_offset + _ANCHOR_BYTES
                        ] == source_raw[
                            source_offset : source_offset + _ANCHOR_BYTES
                        ] and _anchor_closes_256_bytes(
                            public_raw,
                            public_offset,
                            source_raw,
                            source_offset,
                        ):
                            leaked = True
                            break
                    if leaked:
                        break
                if leaked:
                    leaked_public_files += 1
            return leaked_public_files
        finally:
            connection.close()


def _matching_anchor_offsets(
    raw: bytes,
    anchor_hashes: set[bytes] | tuple[np.ndarray, ...],
):
    if len(raw) < _ANCHOR_BYTES or len(anchor_hashes) == 0:
        return
    if isinstance(anchor_hashes, tuple):
        filters = anchor_hashes
    else:
        anchors = np.frombuffer(b"".join(anchor_hashes), dtype="<u8").reshape((-1, 2))
        filters = _build_anchor_filters(anchors)
    chunk_size = 1024 * 1024
    final_start = len(raw) - _ANCHOR_BYTES + 1
    for chunk_start in range(0, final_start, chunk_size):
        chunk_starts = min(chunk_size, final_start - chunk_start)
        for phase in range(_ANCHOR_BYTES):
            if phase >= chunk_starts:
                break
            count = (chunk_starts - phase + _ANCHOR_BYTES - 1) // _ANCHOR_BYTES
            words = np.frombuffer(
                raw,
                dtype="<u8",
                count=count * 2,
                offset=chunk_start + phase,
            )
            first = words[::2]
            second = words[1::2]
            mask = np.uint64((1 << 22) - 1)
            matches = np.flatnonzero(
                filters[0][(first & mask).astype(np.intp)]
                & filters[1][(first >> np.uint64(42)).astype(np.intp)]
                & filters[2][(second & mask).astype(np.intp)]
                & filters[3][(second >> np.uint64(42)).astype(np.intp)]
            )
            for value_index in matches.tolist():
                offset = chunk_start + phase + value_index * _ANCHOR_BYTES
                yield offset, raw[offset : offset + _ANCHOR_BYTES]


def _build_anchor_filters(
    anchors: np.ndarray,
) -> tuple[np.ndarray, ...]:
    filters = tuple(np.zeros(1 << 22, dtype=np.bool_) for _index in range(4))
    mask = np.uint64((1 << 22) - 1)
    filters[0][(anchors[:, 0] & mask).astype(np.intp)] = True
    filters[1][(anchors[:, 0] >> np.uint64(42)).astype(np.intp)] = True
    filters[2][(anchors[:, 1] & mask).astype(np.intp)] = True
    filters[3][(anchors[:, 1] >> np.uint64(42)).astype(np.intp)] = True
    return filters


def _insert_source_anchors(
    connection: sqlite3.Connection, raw: bytes, *, source_index: int
) -> None:
    if len(raw) < _ANCHOR_BYTES:
        return
    batch = []
    for offset in range(0, len(raw) - _ANCHOR_BYTES + 1, _ANCHOR_STRIDE):
        digest = raw[offset : offset + _ANCHOR_BYTES]
        batch.append((digest, source_index, offset))
        if len(batch) == 8192:
            connection.executemany("INSERT INTO source_anchor VALUES (?,?,?)", batch)
            batch.clear()
    if batch:
        connection.executemany("INSERT INTO source_anchor VALUES (?,?,?)", batch)


def _anchor_closes_256_bytes(
    public_raw: bytes,
    public_offset: int,
    source_raw: bytes,
    source_offset: int,
) -> bool:
    left = 0
    while (
        left < _SOURCE_WINDOW_BYTES - _ANCHOR_BYTES
        and public_offset - left > 0
        and source_offset - left > 0
        and public_raw[public_offset - left - 1] == source_raw[source_offset - left - 1]
    ):
        left += 1
    required_right = _SOURCE_WINDOW_BYTES - _ANCHOR_BYTES - left
    public_right = public_raw[
        public_offset + _ANCHOR_BYTES : public_offset + _ANCHOR_BYTES + required_right
    ]
    source_right = source_raw[
        source_offset + _ANCHOR_BYTES : source_offset + _ANCHOR_BYTES + required_right
    ]
    return len(public_right) == required_right and public_right == source_right


def _rolling_windows(raw: bytes):
    yield from _rolling_windows_sized(raw, 256)


def _rolling_windows_sized(raw: bytes, size: int):
    modulus = 1 << 64
    base = 257
    power = pow(base, size - 1, modulus)
    value = _rolling_seed(raw[:size])
    yield 0, value
    for index in range(1, len(raw) - size + 1):
        value = (
            (value - raw[index - 1] * power) * base + raw[index + size - 1]
        ) % modulus
        yield index, value


def _rolling_seed(raw: bytes) -> int:
    value = 0
    for item in raw:
        value = (value * 257 + item) % (1 << 64)
    return value
