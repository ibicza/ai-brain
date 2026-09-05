"""Restart-safe append-only run protocol ledger for M-33.6e."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

M336E_PROTOCOL_VERSION = "m336e.run-protocol.v1"
M336E_PROTOCOL_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")

RUN_PROTOCOL_EVENT_ORDER = (
    "FREEZE_VERIFIED",
    "ACQUISITION_RESERVED",
    "ACQUISITION_COMPLETED",
    "VAULT_SEALED",
    "QUALIFICATION_COMPLETED",
    "SELECTABILITY_CENSUS_COMPLETED",
    "SELECTOR_INVOCATION_RESERVED",
    "SELECTOR_COMPLETED",
    "WINDOWS_PRODUCTION_SEALED",
    "KARINA_PRODUCTION_SEALED",
    "EVALUATION_RESERVED",
    "EVALUATION_COMPLETED",
)


@dataclass(frozen=True)
class RunProtocolEvent:
    schema_version: int
    protocol_version: str
    event_type: str
    event_ordinal: int
    f20_sha: str
    acquisition_run_id: str
    candidate_pool_hash: str
    vault_tree_hash: str | None
    qualification_manifest_hash: str | None
    selectability_census_hash: str | None
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class RunProtocolLedgerReceipt:
    schema_version: int
    protocol_version: str
    f20_sha: str
    acquisition_run_id: str
    candidate_pool_hash: str
    event_count: int
    final_event_type: str | None
    final_event_hash: str | None
    ledger_bytes_sha256: str
    global_acquisition_count: int
    selectability_census_count: int
    selector_invocation_count: int
    selector_rerun_count: int
    production_seal_count: int
    evaluator_start_count: int
    receipt_hash: str


class RunProtocolLedger:
    """A canonical JSONL ledger whose persisted reservations survive restarts."""

    def __init__(self, path: Path, *, git_worktrees=()):
        self.path = path.resolve(strict=False)
        self._git_worktrees = tuple(
            Path(item).resolve(strict=True) for item in git_worktrees
        )
        for worktree in self._git_worktrees:
            if _is_relative_to(self.path, worktree):
                raise ValueError(
                    "run protocol ledger must live outside every Git worktree"
                )

    def events(self) -> tuple[RunProtocolEvent, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if raw and (b"\r" in raw or not raw.endswith(b"\n")):
            raise ValueError("run protocol ledger is not canonical LF JSONL")
        events = []
        for line in raw.splitlines(keepends=True):
            if not line:
                continue
            value = _load_strict_json(line)
            event = _event_from_value(value)
            if (canonical_json(asdict(event)) + "\n").encode("utf-8") != line:
                raise ValueError("run protocol event is not canonical")
            events.append(event)
        _verify_event_chain(tuple(events))
        return tuple(events)

    def append(
        self,
        event_type: str,
        *,
        f20_sha: str,
        acquisition_run_id: str,
        candidate_pool_hash: str,
        vault_tree_hash: str | None = None,
        qualification_manifest_hash: str | None = None,
        selectability_census_hash: str | None = None,
    ) -> RunProtocolEvent:
        lock_path = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = None
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, b"M336E_RUN_PROTOCOL_LOCK\n")
            os.fsync(lock_fd)
            events = self.events()
            expected_ordinal = len(events)
            if expected_ordinal >= len(RUN_PROTOCOL_EVENT_ORDER):
                raise ValueError("run protocol is already complete")
            if event_type != RUN_PROTOCOL_EVENT_ORDER[expected_ordinal]:
                raise ValueError("run protocol event is out of order or repeated")
            _verify_context_fields(
                f20_sha,
                acquisition_run_id,
                candidate_pool_hash,
                vault_tree_hash,
                qualification_manifest_hash,
                selectability_census_hash,
            )
            if events:
                first = events[0]
                if (
                    first.f20_sha != f20_sha
                    or first.acquisition_run_id != acquisition_run_id
                    or first.candidate_pool_hash != candidate_pool_hash
                ):
                    raise ValueError("run protocol identity changed after reservation")
                _require_monotonic_binding(events, "vault_tree_hash", vault_tree_hash)
                _require_monotonic_binding(
                    events, "qualification_manifest_hash", qualification_manifest_hash
                )
                _require_monotonic_binding(
                    events, "selectability_census_hash", selectability_census_hash
                )
            body = {
                "schema_version": M336E_PROTOCOL_SCHEMA_VERSION,
                "protocol_version": M336E_PROTOCOL_VERSION,
                "event_type": event_type,
                "event_ordinal": expected_ordinal,
                "f20_sha": f20_sha,
                "acquisition_run_id": acquisition_run_id,
                "candidate_pool_hash": candidate_pool_hash,
                "vault_tree_hash": vault_tree_hash,
                "qualification_manifest_hash": qualification_manifest_hash,
                "selectability_census_hash": selectability_census_hash,
                "previous_event_hash": events[-1].event_hash if events else None,
            }
            event = RunProtocolEvent(**body, event_hash=content_hash(body))
            encoded = (canonical_json(asdict(event)) + "\n").encode("utf-8")
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if self.events()[-1] != event:
                raise ValueError("persisted run protocol event did not verify")
            return event
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
                lock_path.unlink(missing_ok=True)

    def receipt(self) -> RunProtocolLedgerReceipt:
        events = self.events()
        first = events[0] if events else None
        raw = self.path.read_bytes() if self.path.exists() else b""
        body = {
            "schema_version": M336E_PROTOCOL_SCHEMA_VERSION,
            "protocol_version": M336E_PROTOCOL_VERSION,
            "f20_sha": first.f20_sha if first else "0" * 40,
            "acquisition_run_id": first.acquisition_run_id if first else "UNSTARTED",
            "candidate_pool_hash": first.candidate_pool_hash if first else "0" * 64,
            "event_count": len(events),
            "final_event_type": events[-1].event_type if events else None,
            "final_event_hash": events[-1].event_hash if events else None,
            "ledger_bytes_sha256": bytes_hash(raw),
            "global_acquisition_count": sum(
                item.event_type == "ACQUISITION_COMPLETED" for item in events
            ),
            "selectability_census_count": sum(
                item.event_type == "SELECTABILITY_CENSUS_COMPLETED" for item in events
            ),
            "selector_invocation_count": sum(
                item.event_type == "SELECTOR_COMPLETED" for item in events
            ),
            "selector_rerun_count": max(
                0, sum(item.event_type == "SELECTOR_COMPLETED" for item in events) - 1
            ),
            "production_seal_count": sum(
                item.event_type
                in {"WINDOWS_PRODUCTION_SEALED", "KARINA_PRODUCTION_SEALED"}
                for item in events
            ),
            "evaluator_start_count": sum(
                item.event_type == "EVALUATION_RESERVED" for item in events
            ),
        }
        return RunProtocolLedgerReceipt(**body, receipt_hash=content_hash(body))


def _event_from_value(value) -> RunProtocolEvent:
    expected = set(RunProtocolEvent.__dataclass_fields__)
    if set(value) != expected:
        raise ValueError("run protocol event has unknown or missing fields")
    event = RunProtocolEvent(**value)
    body = asdict(event)
    claimed = body.pop("event_hash")
    _verify_context_fields(
        event.f20_sha,
        event.acquisition_run_id,
        event.candidate_pool_hash,
        event.vault_tree_hash,
        event.qualification_manifest_hash,
        event.selectability_census_hash,
    )
    if (
        event.schema_version != M336E_PROTOCOL_SCHEMA_VERSION
        or event.protocol_version != M336E_PROTOCOL_VERSION
        or event.event_type not in RUN_PROTOCOL_EVENT_ORDER
        or content_hash(body) != claimed
    ):
        raise ValueError("run protocol event is invalid")
    return event


def _verify_event_chain(events) -> None:
    context = None
    bindings = {
        "vault_tree_hash": None,
        "qualification_manifest_hash": None,
        "selectability_census_hash": None,
    }
    previous = None
    for ordinal, event in enumerate(events):
        if (
            event.event_ordinal != ordinal
            or event.event_type != RUN_PROTOCOL_EVENT_ORDER[ordinal]
            or event.previous_event_hash != previous
        ):
            raise ValueError("run protocol event order/hash chain is invalid")
        identity = (event.f20_sha, event.acquisition_run_id, event.candidate_pool_hash)
        if context is None:
            context = identity
        elif context != identity:
            raise ValueError("run protocol identity changed within the chain")
        for field, bound in bindings.items():
            value = getattr(event, field)
            if bound is not None and value != bound:
                raise ValueError(
                    "run protocol evidence binding changed within the chain"
                )
            if value is not None:
                bindings[field] = value
        previous = event.event_hash


def _verify_context_fields(f20_sha, run_id, pool_hash, *optional_hashes) -> None:
    if _GIT_SHA.fullmatch(f20_sha) is None:
        raise ValueError("run protocol requires an exact freeze SHA")
    if not run_id:
        raise ValueError("run protocol acquisition run ID is empty")
    if _SHA256.fullmatch(pool_hash) is None or any(
        value is not None and _SHA256.fullmatch(value) is None
        for value in optional_hashes
    ):
        raise ValueError("run protocol contains an invalid SHA-256 binding")


def _require_monotonic_binding(events, field, value) -> None:
    prior = next(
        (
            getattr(event, field)
            for event in reversed(events)
            if getattr(event, field) is not None
        ),
        None,
    )
    if prior is not None and value != prior:
        raise ValueError("run protocol evidence binding was removed or changed")


def _load_strict_json(raw: bytes):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("run protocol JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("run protocol JSON is malformed") from exc


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
