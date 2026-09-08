"""Persistent state authority for the real M-33.6i final controller."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

M336I_ROUTE_STATES = (
    "INITIAL",
    "PREFLIGHT_PASSED",
    "AUTHORIZATION_VALIDATED",
    "ACQUISITION_RESERVED",
    "ACQUISITION_COMPLETED",
    "ACQUISITION_INPUT_BOUND",
    "VAULT_PORTABILITY_VERIFIED",
    "QUALIFICATION_SEALED",
    "CENSUS_SEALED",
    "COMPILATION_CLOSURE_SEALED",
    "CLOSURE_FEASIBILITY_PASSED",
    "SELECTOR_RESERVED",
    "SELECTION_COMPLETED",
    "SOURCE_SNAPSHOT_MATERIALIZED_WINDOWS",
    "SOURCE_SNAPSHOT_MATERIALIZED_KARINA",
    "WINDOWS_PRODUCTION_SEALED",
    "KARINA_PRODUCTION_SEALED",
    "CROSS_PLATFORM_PRODUCTION_VERIFIED",
    "PUBLIC_PACK_VERIFIED",
    "SEALED_REPLAY_VERIFIED_WINDOWS",
    "SEALED_REPLAY_VERIFIED_KARINA",
    "EVALUATOR_RESERVED",
    "EVALUATION_COMPLETED",
    "PUBLIC_STAGING_VALIDATED",
    "OUTCOME_A_READY",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class M336IRouteStateEvent:
    schema_version: int
    route_version: str
    state: str
    ordinal: int
    context_hash: str
    operation_receipt_hash: str
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class M336IRouteStateLedgerReceipt:
    schema_version: int
    route_version: str
    context_hash: str | None
    state_count: int
    final_state: str | None
    final_event_hash: str | None
    ledger_bytes_hash: str
    complete: bool
    receipt_hash: str


class M336IRouteStateLedger:
    """Canonical external state ledger advanced by production orchestration."""

    def __init__(self, path: Path, *, git_worktrees=()):
        self.path = path.resolve(strict=False)
        roots = tuple(Path(item).resolve(strict=True) for item in git_worktrees)
        if any(self.path.is_relative_to(root) for root in roots):
            raise ValueError("M336I route-state ledger must remain outside Git")

    def events(self) -> tuple[M336IRouteStateEvent, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if raw and (b"\r" in raw or not raw.endswith(b"\n")):
            raise ValueError("M336I route-state ledger is not canonical LF JSONL")
        events = []
        previous = None
        context = None
        for ordinal, line in enumerate(raw.splitlines()):
            value = _strict_json(line)
            if set(value) != set(M336IRouteStateEvent.__dataclass_fields__):
                raise ValueError("M336I route-state event fields changed")
            event = M336IRouteStateEvent(**value)
            body = asdict(event)
            claimed = body.pop("event_hash")
            if (
                event.schema_version != 1
                or event.route_version != "m336i.authorized-final-java-route.v1"
                or ordinal >= len(M336I_ROUTE_STATES)
                or event.ordinal != ordinal
                or event.state != M336I_ROUTE_STATES[ordinal]
                or event.previous_event_hash != previous
                or _SHA256.fullmatch(event.context_hash) is None
                or _SHA256.fullmatch(event.operation_receipt_hash) is None
                or content_hash(body) != claimed
            ):
                raise ValueError("M336I route-state chain is invalid")
            if context is None:
                context = event.context_hash
            elif context != event.context_hash:
                raise ValueError("M336I route-state context changed")
            events.append(event)
            previous = event.event_hash
        return tuple(events)

    def advance(
        self, state: str, *, context_hash: str, operation_receipt_hash: str
    ) -> M336IRouteStateEvent:
        if (
            _SHA256.fullmatch(context_hash) is None
            or _SHA256.fullmatch(operation_receipt_hash) is None
        ):
            raise ValueError("M336I route transition requires SHA-256 bindings")
        lock = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, b"M336I_ROUTE_STATE_LOCK\n")
            os.fsync(descriptor)
            prior = self.events()
            if len(prior) >= len(M336I_ROUTE_STATES):
                raise ValueError("M336I route is already terminal")
            if state != M336I_ROUTE_STATES[len(prior)]:
                raise ValueError("M336I route transition is skipped or repeated")
            if prior and prior[0].context_hash != context_hash:
                raise ValueError("M336I route transition context changed")
            body = {
                "schema_version": 1,
                "route_version": "m336i.authorized-final-java-route.v1",
                "state": state,
                "ordinal": len(prior),
                "context_hash": context_hash,
                "operation_receipt_hash": operation_receipt_hash,
                "previous_event_hash": prior[-1].event_hash if prior else None,
            }
            event = M336IRouteStateEvent(**body, event_hash=content_hash(body))
            encoded = (canonical_json(asdict(event)) + "\n").encode("utf-8")
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if self.events()[-1] != event:
                raise ValueError("M336I route transition did not persist")
            return event
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)

    def receipt(self) -> M336IRouteStateLedgerReceipt:
        events = self.events()
        body = {
            "schema_version": 1,
            "route_version": "m336i.authorized-final-java-route.v1",
            "context_hash": events[0].context_hash if events else None,
            "state_count": len(events),
            "final_state": events[-1].state if events else None,
            "final_event_hash": events[-1].event_hash if events else None,
            "ledger_bytes_hash": bytes_hash(self.path.read_bytes())
            if self.path.exists()
            else bytes_hash(b""),
            "complete": len(events) == len(M336I_ROUTE_STATES),
        }
        return M336IRouteStateLedgerReceipt(**body, receipt_hash=content_hash(body))


def _strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("M336I route-state JSON has a duplicate key")
            result[key] = value
        return result

    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
