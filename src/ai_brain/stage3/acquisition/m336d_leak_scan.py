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

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash


def scan_fresh_source_leaks(vault: Path, public: Path | tuple[Path, ...]) -> dict:
    """Reject exact source bodies, encodings, paths, and 256-byte windows.

    The exact window join is disk-backed.  The rolling hash is only an index:
    every joined candidate is compared byte-for-byte before it counts as a leak.
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
    vault_text = str(vault.resolve())
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
            absolute += int(
                vault_text in text
                or bool(re.search(r"(?:[A-Za-z]:\\|/home/|/tmp/)", text))
            )
    source_window = _source_window_leak_count(java_files, public_files)
    counts = {
        "exact_source_jar_body_count": exact_source_jar,
        "exact_scm_archive_body_count": exact_scm,
        "complete_extracted_java_file_count": exact_java,
        "exact_256_byte_source_window_count": source_window,
        "base64_or_hex_source_body_count": encoded,
        "local_vault_absolute_path_count": absolute,
        "raw_license_document_body_count": legal,
        "source_excerpt_publication_receipt_count": 0,
    }
    total = sum(counts.values())
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
                "CREATE TABLE source_window "
                "(rolling_hash BLOB NOT NULL, source_index INTEGER NOT NULL, "
                "source_offset INTEGER NOT NULL)"
            )
            for source_index, path in enumerate(source_paths):
                _insert_windows(
                    connection,
                    "source_window",
                    path.read_bytes(),
                    source_index,
                )
            connection.execute(
                "CREATE INDEX source_window_hash ON source_window(rolling_hash)"
            )
            connection.execute(
                "CREATE TEMP TABLE public_window "
                "(rolling_hash BLOB NOT NULL, public_offset INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX public_window_hash ON public_window(rolling_hash)"
            )
            source_cache: dict[int, bytes] = {}
            leaked_public_files = 0
            for path in public_paths:
                public_raw = path.read_bytes()
                if len(public_raw) < 256:
                    continue
                connection.execute("DELETE FROM public_window")
                _insert_windows(connection, "public_window", public_raw)
                cursor = connection.execute(
                    "SELECT p.public_offset, s.source_index, s.source_offset "
                    "FROM public_window AS p JOIN source_window AS s "
                    "ON p.rolling_hash = s.rolling_hash"
                )
                leaked = False
                for public_offset, source_index, source_offset in cursor:
                    source_raw = source_cache.get(source_index)
                    if source_raw is None:
                        source_raw = source_paths[source_index].read_bytes()
                        source_cache.clear()
                        source_cache[source_index] = source_raw
                    if (
                        public_raw[public_offset : public_offset + 256]
                        == source_raw[source_offset : source_offset + 256]
                    ):
                        leaked = True
                        break
                if leaked:
                    leaked_public_files += 1
            return leaked_public_files
        finally:
            connection.close()


def _insert_windows(
    connection: sqlite3.Connection,
    table: str,
    raw: bytes,
    item_index: int | None = None,
) -> None:
    if len(raw) < 256:
        return
    batch = []
    for offset, value in _rolling_windows(raw):
        digest = value.to_bytes(8, "big")
        batch.append(
            (digest, item_index, offset) if item_index is not None else (digest, offset)
        )
        if len(batch) == 8192:
            _insert_window_batch(connection, table, batch, item_index is not None)
            batch.clear()
    if batch:
        _insert_window_batch(connection, table, batch, item_index is not None)


def _insert_window_batch(
    connection, table: str, rows: list[tuple], source: bool
) -> None:
    if table not in {"source_window", "public_window"}:
        raise ValueError("invalid leak-index table")
    placeholders = "?,?,?" if source else "?,?"
    connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def _rolling_windows(raw: bytes):
    modulus = 1 << 64
    base = 257
    power = pow(base, 255, modulus)
    value = _rolling_seed(raw[:256])
    yield 0, value
    for index in range(1, len(raw) - 255):
        value = ((value - raw[index - 1] * power) * base + raw[index + 255]) % modulus
        yield index, value


def _rolling_seed(raw: bytes) -> int:
    value = 0
    for item in raw:
        value = (value * 257 + item) % (1 << 64)
    return value
