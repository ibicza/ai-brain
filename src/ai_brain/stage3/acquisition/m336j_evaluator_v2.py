"""One-shot evaluator reservation that precedes all M-33.6j.3 golden work."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    strict_json_loads,
)
from ai_brain.stage3.acquisition.m336j_final_v2 import M336J3_EVALUATION_RUN_ID

M336J3_EVALUATOR_EVENTS = (
    "WINDOWS_PRODUCTION_SEALED",
    "KARINA_PRODUCTION_SEALED",
    "CROSS_PLATFORM_PRODUCTION_VERIFIED",
    "EVALUATOR_RESERVED",
    "INDEPENDENT_GOLDEN_GENERATION_STARTED",
    "INDEPENDENT_GOLDEN_GENERATION_COMPLETED",
    "INDEPENDENT_EVALUATION_COMPLETED",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class M336JEvaluatorReservationInputV2:
    windows_production_seal: Path
    karina_production_seal: Path
    selected_manifest: Path
    sealed_vault: Path
    evaluator_implementation_hash: str
    evaluator_jdk_identity_hash: str
    golden_output_destination: Path
    evaluation_run_id: str


@dataclass(frozen=True)
class M336JEvaluatorEventV2:
    schema_version: int
    route_version: str
    event: str
    ordinal: int
    context_hash: str
    operation_hash: str
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class M336JEvaluatorReservationReceiptV2:
    schema_version: int
    contract_role: str
    context_hash: str
    windows_production_seal_hash: str
    karina_production_seal_hash: str
    selected_manifest_hash: str
    sealed_vault_tree_hash: str
    evaluator_implementation_hash: str
    evaluator_jdk_identity_hash: str
    golden_output_destination_hash: str
    evaluation_run_id: str
    evaluator_reservation_count: int
    status: str
    receipt_hash: str


class M336JEvaluatorLedgerV2:
    def __init__(self, path: Path, *, git_worktrees: tuple[Path, ...] = ()) -> None:
        self.path = path.resolve(strict=False)
        for root in git_worktrees:
            repository = root.resolve(strict=True)
            if self.path == repository or self.path.is_relative_to(repository):
                raise ValueError("M336J V2 evaluator ledger must remain outside Git")

    def events(self) -> tuple[M336JEvaluatorEventV2, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if b"\r" in raw or (raw and not raw.endswith(b"\n")):
            raise ValueError("M336J V2 evaluator ledger is not canonical LF JSONL")
        result = []
        previous = None
        context = None
        for ordinal, line in enumerate(raw.splitlines()):
            value = strict_json_loads(line)
            if not isinstance(value, dict) or set(value) != {
                item.name
                for item in M336JEvaluatorEventV2.__dataclass_fields__.values()
            }:
                raise ValueError("M336J V2 evaluator event fields changed")
            event = M336JEvaluatorEventV2(**value)
            body = asdict(event)
            claimed = body.pop("event_hash")
            if (
                event.schema_version != 2
                or event.route_version != "m336j3.final-evaluator.v2"
                or ordinal >= len(M336J3_EVALUATOR_EVENTS)
                or event.ordinal != ordinal
                or event.event != M336J3_EVALUATOR_EVENTS[ordinal]
                or event.previous_event_hash != previous
                or _SHA256.fullmatch(event.context_hash) is None
                or _SHA256.fullmatch(event.operation_hash) is None
                or content_hash(body) != claimed
            ):
                raise ValueError("M336J V2 evaluator event chain is invalid")
            if context is None:
                context = event.context_hash
            elif context != event.context_hash:
                raise ValueError("M336J V2 evaluator context changed")
            result.append(event)
            previous = event.event_hash
        return tuple(result)

    def append(self, event: str, *, context_hash: str, operation_hash: str) -> None:
        if (
            _SHA256.fullmatch(context_hash) is None
            or _SHA256.fullmatch(operation_hash) is None
        ):
            raise ValueError("M336J V2 evaluator transition lacks SHA-256 bindings")
        lock = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, b"M336J3_EVALUATOR_LOCK\n")
            os.fsync(descriptor)
            prior = self.events()
            if (
                len(prior) >= len(M336J3_EVALUATOR_EVENTS)
                or event != M336J3_EVALUATOR_EVENTS[len(prior)]
            ):
                raise ValueError("M336J V2 evaluator state is skipped or repeated")
            if prior and prior[0].context_hash != context_hash:
                raise ValueError("M336J V2 evaluator context changed")
            body = {
                "schema_version": 2,
                "route_version": "m336j3.final-evaluator.v2",
                "event": event,
                "ordinal": len(prior),
                "context_hash": context_hash,
                "operation_hash": operation_hash,
                "previous_event_hash": prior[-1].event_hash if prior else None,
            }
            encoded = (
                canonical_json({**body, "event_hash": content_hash(body)}) + "\n"
            ).encode("utf-8")
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self.events()
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)


def reserve_m336j_evaluator_v2(
    request: M336JEvaluatorReservationInputV2,
    ledger: M336JEvaluatorLedgerV2,
) -> M336JEvaluatorReservationReceiptV2:
    if not isinstance(request, M336JEvaluatorReservationInputV2):
        raise TypeError("M336J V2 evaluator reservation requires typed input")
    if ledger.events():
        raise ValueError("M336J V2 evaluator capacity is already used or blocked")
    if request.golden_output_destination.exists():
        raise FileExistsError("M336J V2 golden output must be fresh at reservation")
    windows = _verified(request.windows_production_seal, "seal_hash", "WINDOWS")
    karina = _verified(request.karina_production_seal, "seal_hash", "KARINA")
    selected = _verified(request.selected_manifest, "manifest_hash")
    vault_hash = _tree_hash(request.sealed_vault)
    if (
        request.evaluation_run_id != M336J3_EVALUATION_RUN_ID
        or not _is_hash(request.evaluator_implementation_hash)
        or not _is_hash(request.evaluator_jdk_identity_hash)
    ):
        raise ValueError("M336J V2 evaluator reservation identity is invalid")
    neutral_exclusions = {
        "platform_role",
        "production_request_hash",
        "production_response_hash",
        "seal_hash",
    }
    if {
        key: value for key, value in windows.items() if key not in neutral_exclusions
    } != {key: value for key, value in karina.items() if key not in neutral_exclusions}:
        raise ValueError("M336J V2 platform production seals differ")
    golden_destination_hash = content_hash(
        str(request.golden_output_destination.resolve(strict=False))
    )
    context = content_hash(
        (
            windows["seal_hash"],
            karina["seal_hash"],
            selected["manifest_hash"],
            vault_hash,
            request.evaluator_implementation_hash,
            request.evaluator_jdk_identity_hash,
            golden_destination_hash,
            request.evaluation_run_id,
        )
    )
    for event, operation in (
        ("WINDOWS_PRODUCTION_SEALED", windows["seal_hash"]),
        ("KARINA_PRODUCTION_SEALED", karina["seal_hash"]),
        (
            "CROSS_PLATFORM_PRODUCTION_VERIFIED",
            content_hash((windows["seal_hash"], karina["seal_hash"])),
        ),
        ("EVALUATOR_RESERVED", context),
    ):
        ledger.append(event, context_hash=context, operation_hash=operation)
    body = {
        "schema_version": 2,
        "contract_role": "M336J_EVALUATOR_RESERVATION_RECEIPT_V2",
        "context_hash": context,
        "windows_production_seal_hash": windows["seal_hash"],
        "karina_production_seal_hash": karina["seal_hash"],
        "selected_manifest_hash": selected["manifest_hash"],
        "sealed_vault_tree_hash": vault_hash,
        "evaluator_implementation_hash": request.evaluator_implementation_hash,
        "evaluator_jdk_identity_hash": request.evaluator_jdk_identity_hash,
        "golden_output_destination_hash": golden_destination_hash,
        "evaluation_run_id": request.evaluation_run_id,
        "evaluator_reservation_count": 1,
        "status": "PASS",
    }
    return M336JEvaluatorReservationReceiptV2(**body, receipt_hash=content_hash(body))


def advance_m336j_evaluator_v2(
    ledger: M336JEvaluatorLedgerV2,
    event: str,
    *,
    context_hash: str,
    operation_hash: str,
) -> None:
    if event not in M336J3_EVALUATOR_EVENTS[4:]:
        raise ValueError("M336J V2 evaluator continuation event is invalid")
    ledger.append(event, context_hash=context_hash, operation_hash=operation_hash)


def verify_m336j_evaluator_ready_for_evaluation_v2(
    ledger: M336JEvaluatorLedgerV2,
    *,
    context_hash: str,
) -> None:
    events = ledger.events()
    if tuple(item.event for item in events) != M336J3_EVALUATOR_EVENTS[:6] or any(
        item.context_hash != context_hash for item in events
    ):
        raise ValueError(
            "M336J V2 evaluation requires one reserved and completed golden run"
        )


def _verified(path: Path, hash_field: str, platform: str | None = None) -> dict:
    value = strict_json_file(path.resolve(strict=True))
    if not isinstance(value, dict):
        raise TypeError("M336J V2 evaluator input is not an object")
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if (
        content_hash(body) != claimed
        or (platform is not None and value.get("platform_role") != platform)
        or (platform is not None and value.get("status") != "PASS")
    ):
        raise ValueError("M336J V2 evaluator input is invalid")
    return value


def _tree_hash(root: Path) -> str:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("M336J V2 sealed vault is not a directory")
    rows = tuple(
        (path.relative_to(resolved).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in resolved.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(resolved).as_posix().encode("utf-8"),
        )
    )
    if not rows:
        raise ValueError("M336J V2 sealed vault is empty")
    return content_hash(rows)


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
