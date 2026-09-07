"""Independent, count-neutral evaluation for sealed M-33.6h production."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336h_contracts import (
    SCHEMA_HASHES,
    strict_json_file,
)

_EVALUATOR_EVENTS = (
    "WINDOWS_PRODUCTION_SEALED",
    "KARINA_PRODUCTION_SEALED",
    "EVALUATOR_RESERVED",
    "EVALUATOR_COMPLETED",
)


@dataclass(frozen=True)
class M336HIndependentJavaEvaluationRequest:
    route_manifest: Path
    threshold_manifest: Path
    windows_production_seal: Path
    karina_production_seal: Path
    public_candidate_pack: Path
    public_replay_commitment: Path
    sealed_source_replay_receipts: tuple[Path, Path]
    independent_reference_material: Path
    evaluator_reservation_ledger: Path


@dataclass(frozen=True)
class M336HIndependentJavaEvaluationResult:
    schema_version: int
    contract_role: str
    request_hash: str
    request_schema_hash: str
    response_schema_hash: str
    route_manifest_hash: str
    threshold_manifest_hash: str
    windows_production_seal_hash: str
    karina_production_seal_hash: str
    public_candidate_pack_hash: str
    public_candidate_pack_tree_hash: str
    public_replay_commitment_hash: str
    independent_reference_hash: str
    proposal_count: int
    trusted_count: int
    withheld_count: int
    trusted_binding_identity_match: bool
    field_evidence_identity_match: bool
    trust_precision: str
    trust_coverage: str
    location_precision: str
    location_recall: str
    semantic_precision: str
    semantic_recall: str
    field_evidence_exactness: str
    spdx_agreement: str
    wrong_trusted_count: int
    false_automatic_spdx_identity_count: int
    runtime_status: str
    pack_integrity_status: str
    sealed_replay_status: str
    platform_neutral_difference_count: int
    production_call_count: int
    selector_call_count: int
    source_materialization_count: int
    network_access_count: int
    torch_import_count: int
    structural_invariants_satisfied: bool
    status: str
    result_hash: str


class M336HEvaluatorLedger:
    def __init__(self, path: Path, *, git_worktrees: tuple[Path, ...] = ()) -> None:
        self.path = path.resolve(strict=False)
        for root in git_worktrees:
            resolved = root.resolve(strict=True)
            if self.path == resolved or self.path.is_relative_to(resolved):
                raise ValueError("M336H evaluator ledger must be external")

    def events(self) -> tuple[dict, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if b"\r" in raw or (raw and not raw.endswith(b"\n")):
            raise ValueError("M336H evaluator ledger is not canonical LF JSONL")
        result = []
        previous = None
        for ordinal, line in enumerate(raw.splitlines()):
            value = json.loads(line.decode("utf-8"))
            claimed = value.pop("event_hash", None)
            if (
                set(value)
                != {"schema_version", "event", "ordinal", "context_hash", "previous"}
                or ordinal >= len(_EVALUATOR_EVENTS)
                or value["event"] != _EVALUATOR_EVENTS[ordinal]
                or value["ordinal"] != ordinal
                or value["previous"] != previous
                or content_hash(value) != claimed
            ):
                raise ValueError("M336H evaluator ledger chain is invalid")
            value["event_hash"] = claimed
            result.append(value)
            previous = claimed
        return tuple(result)

    def append(self, event: str, *, context_hash: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        descriptor = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            events = self.events()
            if (
                len(events) >= len(_EVALUATOR_EVENTS)
                or event != _EVALUATOR_EVENTS[len(events)]
            ):
                raise ValueError("M336H evaluator state is skipped or repeated")
            if events and events[0]["context_hash"] != context_hash:
                raise ValueError("M336H evaluator context changed")
            body = {
                "schema_version": 1,
                "event": event,
                "ordinal": len(events),
                "context_hash": context_hash,
                "previous": events[-1]["event_hash"] if events else None,
            }
            encoded = (
                json.dumps(
                    {**body, "event_hash": content_hash(body)},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self.events()
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)


def _load(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336H evaluator input must be an object")
    return value


def _verify_hashed(value: dict, field: str, *, status_field: str | None = None) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError("M336H evaluator input hash mismatch")
    if status_field is not None and value.get(status_field) != "PASS":
        raise ValueError("M336H evaluator input is not sealed PASS")


def _request_body(request: M336HIndependentJavaEvaluationRequest) -> dict:
    return {
        item.name: tuple(str(value) for value in getattr(request, item.name))
        if item.name == "sealed_source_replay_receipts"
        else str(getattr(request, item.name))
        for item in fields(request)
    }


def evaluation_request_from_dict(
    value: dict,
) -> M336HIndependentJavaEvaluationRequest:
    expected = {item.name for item in fields(M336HIndependentJavaEvaluationRequest)}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("M336H independent evaluation request is incomplete")
    paths = {
        key: tuple(Path(item) for item in item_value)
        if key == "sealed_source_replay_receipts"
        else Path(item_value)
        for key, item_value in value.items()
    }
    request = M336HIndependentJavaEvaluationRequest(**paths)
    if len(request.sealed_source_replay_receipts) != 2:
        raise ValueError("M336H evaluator requires exactly two replay receipts")
    return request


def _binding_evidence(pack: Path) -> tuple[str, str, int]:
    bindings = strict_json_file(pack / "source_bindings.json")
    if not isinstance(bindings, list):
        raise TypeError("M336H public source bindings are not an array")
    binding_ids = tuple(sorted(item["binding_id"] for item in bindings))
    field_rows = tuple(
        sorted(
            (item["binding_id"], tuple(tuple(row) for row in item["field_evidence"]))
            for item in bindings
        )
    )
    return content_hash(binding_ids), content_hash(field_rows), len(bindings)


def _neutral_seal_body(value: dict) -> dict:
    excluded = {
        "platform_role",
        "production_request_hash",
        "production_response_hash",
        "seal_hash",
    }
    return {key: item for key, item in value.items() if key not in excluded}


def run_m336h_independent_java_evaluation(
    request: M336HIndependentJavaEvaluationRequest,
) -> M336HIndependentJavaEvaluationResult:
    """Evaluate only sealed public inputs after both platform productions."""

    if not isinstance(request, M336HIndependentJavaEvaluationRequest):
        raise TypeError("M336H evaluator requires its exact typed request")
    for path in (
        request.route_manifest,
        request.threshold_manifest,
        request.windows_production_seal,
        request.karina_production_seal,
        request.public_candidate_pack,
        request.public_replay_commitment,
        *request.sealed_source_replay_receipts,
        request.independent_reference_material,
    ):
        if not path.exists():
            raise ValueError("M336H evaluator input is missing")
    if request.evaluator_reservation_ledger.exists():
        raise FileExistsError("M336H evaluator ledger must be fresh")

    route = _load(request.route_manifest)
    thresholds = _load(request.threshold_manifest)
    windows = _load(request.windows_production_seal)
    karina = _load(request.karina_production_seal)
    reference = _load(request.independent_reference_material)
    replays = tuple(_load(path) for path in request.sealed_source_replay_receipts)
    _verify_hashed(route, "manifest_hash")
    _verify_hashed(thresholds, "threshold_manifest_hash")
    _verify_hashed(windows, "seal_hash", status_field="status")
    _verify_hashed(karina, "seal_hash", status_field="status")
    _verify_hashed(reference, "reference_hash")
    for replay in replays:
        _verify_hashed(replay, "receipt_hash", status_field="status")
    if (
        windows.get("platform_role") != "WINDOWS"
        or karina.get("platform_role") != "KARINA"
    ):
        raise ValueError("M336H evaluator requires both ordered production seals")
    if (
        windows["route_manifest_hash"] != route["manifest_hash"]
        or karina["route_manifest_hash"] != route["manifest_hash"]
    ):
        raise ValueError("M336H evaluator route binding differs")
    neutral_difference_count = int(
        _neutral_seal_body(windows) != _neutral_seal_body(karina)
    )
    pack_receipt = verify_java_public_candidate_pack(request.public_candidate_pack)
    commitment = _load(request.public_replay_commitment)
    if request.public_replay_commitment.resolve(strict=True) != (
        request.public_candidate_pack / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME
    ).resolve(strict=True):
        raise ValueError("M336H evaluator commitment is not the pack commitment")
    _verify_hashed(commitment, "commitment_hash")
    binding_hash, field_hash, trusted_count = _binding_evidence(
        request.public_candidate_pack
    )
    trusted_match = binding_hash == reference["expected_trusted_binding_id_hash"]
    field_match = field_hash == reference["expected_field_evidence_hash"]
    metrics = reference["metrics"]
    required_metrics = {
        "trust_precision",
        "trust_coverage",
        "location_precision",
        "location_recall",
        "semantic_precision",
        "semantic_recall",
        "field_evidence_exactness",
        "spdx_agreement",
    }
    if not isinstance(metrics, dict) or set(metrics) != required_metrics:
        raise ValueError("M336H independent metric denominator changed")
    minimums = thresholds["minimum_metrics"]
    metric_pass = all(
        Decimal(str(metrics[name])) >= Decimal(str(minimums[name]))
        for name in required_metrics
    )
    replay_pass = all(
        item["status"] == "PASS"
        and item["reconstructed_pack_byte_difference_count"] == 0
        and item["public_replay_commitment_hash"] == commitment["commitment_hash"]
        for item in replays
    )
    counts_match = (
        windows["trusted_count"] == trusted_count == karina["trusted_count"]
        and windows["proposal_count"]
        == windows["trusted_count"] + windows["withheld_count"]
        and karina["proposal_count"]
        == karina["trusted_count"] + karina["withheld_count"]
    )
    structural = (
        neutral_difference_count == 0
        and pack_receipt.status == "PASS"
        and pack_receipt.candidate_pack_content_hash
        == reference["expected_candidate_pack_hash"]
        and windows["public_candidate_pack_hash"]
        == karina["public_candidate_pack_hash"]
        == pack_receipt.candidate_pack_content_hash
        and windows["public_replay_commitment_hash"]
        == karina["public_replay_commitment_hash"]
        == commitment["commitment_hash"]
        and trusted_match
        and field_match
        and counts_match
        and replay_pass
        and metric_pass
        and reference["wrong_trusted_count"]
        <= thresholds["maximum_wrong_trusted_count"]
        and reference["false_automatic_spdx_identity_count"]
        <= thresholds["maximum_false_automatic_spdx_identity_count"]
        and reference["runtime_status"] == "PASS"
    )
    request_hash = content_hash(_request_body(request))
    context_hash = content_hash(
        (request_hash, windows["seal_hash"], karina["seal_hash"])
    )
    ledger = M336HEvaluatorLedger(request.evaluator_reservation_ledger)
    ledger.append("WINDOWS_PRODUCTION_SEALED", context_hash=context_hash)
    ledger.append("KARINA_PRODUCTION_SEALED", context_hash=context_hash)
    ledger.append("EVALUATOR_RESERVED", context_hash=context_hash)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_EVALUATION",
        "request_hash": request_hash,
        "request_schema_hash": SCHEMA_HASHES["evaluation_request"],
        "response_schema_hash": SCHEMA_HASHES["evaluation_result"],
        "route_manifest_hash": route["manifest_hash"],
        "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
        "windows_production_seal_hash": windows["seal_hash"],
        "karina_production_seal_hash": karina["seal_hash"],
        "public_candidate_pack_hash": pack_receipt.candidate_pack_content_hash,
        "public_candidate_pack_tree_hash": pack_receipt.candidate_pack_tree_hash,
        "public_replay_commitment_hash": commitment["commitment_hash"],
        "independent_reference_hash": reference["reference_hash"],
        "proposal_count": windows["proposal_count"],
        "trusted_count": trusted_count,
        "withheld_count": windows["withheld_count"],
        "trusted_binding_identity_match": trusted_match,
        "field_evidence_identity_match": field_match,
        **metrics,
        "wrong_trusted_count": reference["wrong_trusted_count"],
        "false_automatic_spdx_identity_count": reference[
            "false_automatic_spdx_identity_count"
        ],
        "runtime_status": reference["runtime_status"],
        "pack_integrity_status": pack_receipt.status,
        "sealed_replay_status": "PASS" if replay_pass else "FAIL",
        "platform_neutral_difference_count": neutral_difference_count,
        "production_call_count": 0,
        "selector_call_count": 0,
        "source_materialization_count": 0,
        "network_access_count": 0,
        "torch_import_count": 0,
        "structural_invariants_satisfied": structural,
        "status": "PASS" if structural else "FAIL",
    }
    result = M336HIndependentJavaEvaluationResult(
        **body, result_hash=content_hash(body)
    )
    ledger.append("EVALUATOR_COMPLETED", context_hash=context_hash)
    if result.status != "PASS":
        raise ValueError("M336H independent count-neutral evaluation failed")
    return result


def evaluation_result_from_dict(value: dict) -> M336HIndependentJavaEvaluationResult:
    if set(value) != set(M336HIndependentJavaEvaluationResult.__dataclass_fields__):
        raise ValueError("M336H evaluation result schema changed")
    result = M336HIndependentJavaEvaluationResult(**value)
    body = asdict(result)
    claimed = body.pop("result_hash")
    if content_hash(body) != claimed or result.status != "PASS":
        raise ValueError("M336H independent evaluation result is invalid")
    return result
