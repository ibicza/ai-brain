"""One-shot closure-aware M-33.6f Java source selection."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_identity import (
    SourceEntryBindingManifest,
    verify_source_entry_binding_manifest,
)
from ai_brain.stage3.acquisition.m336e_selectability import SelectableSourceCensus
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    JavaCompilationClosureFeasibilityProof,
    JavaCompilationClosureManifest,
    verify_java_compilation_closure_feasibility_proof,
)

M336F_SELECTOR_VERSION = "m336f.compilation-closure-selector.v1"
_EVENT_ORDER = ("CENSUS_SEALED", "SELECTOR_RESERVED", "SELECTOR_COMPLETED")


@dataclass(frozen=True)
class M336FSelectedSource:
    source_entry_identity_hash: str
    candidate_root: str
    canonical_path: str
    selected_path: str
    selection_role: str
    selection_rank: str
    row_hash: str


@dataclass(frozen=True)
class M336FSelectedSourceManifest:
    schema_version: int
    qualification_report_hash: str
    qualification_summary_hash: str
    census_hash: str
    closure_manifest_hash: str
    feasibility_proof_hash: str
    binding_manifest_hash: str
    file_count: int
    root_count: int
    root_distribution: tuple[tuple[str, int], ...]
    semantic_file_count: int
    closure_support_file_count: int
    files: tuple[M336FSelectedSource, ...]
    manifest_hash: str


@dataclass(frozen=True)
class M336FSelectorReceipt:
    schema_version: int
    selector_version: str
    selector_seed_hash: str
    qualification_report_hash: str
    qualification_summary_hash: str
    census_hash: str
    closure_manifest_hash: str
    feasibility_proof_hash: str
    binding_manifest_hash: str
    selector_reservation_count: int
    selector_invocation_count: int
    selector_rerun_count: int
    evaluator_read_count: int
    golden_read_count: int
    trust_metric_read_count: int
    selected_manifest_hash: str
    receipt_hash: str


class M336FSelectorLedger:
    def __init__(self, path: Path, *, git_worktrees=()):
        self.path = path.resolve(strict=False)
        roots = tuple(Path(item).resolve(strict=True) for item in git_worktrees)
        if any(self.path.is_relative_to(root) for root in roots):
            raise ValueError("selector ledger must live outside every Git worktree")

    def events(self) -> tuple[dict, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if raw and (b"\r" in raw or not raw.endswith(b"\n")):
            raise ValueError("selector ledger is not canonical LF JSONL")
        result = []
        previous = None
        for ordinal, line in enumerate(raw.splitlines()):
            value = json.loads(line.decode("utf-8", errors="strict"))
            claimed = value.pop("event_hash")
            if (
                set(value)
                != {"schema_version", "event", "ordinal", "context_hash", "previous"}
                or value["schema_version"] != 1
                or value["event"] != _EVENT_ORDER[ordinal]
                or value["ordinal"] != ordinal
                or value["previous"] != previous
                or content_hash(value) != claimed
            ):
                raise ValueError("selector ledger event chain is invalid")
            value["event_hash"] = claimed
            result.append(value)
            previous = claimed
        return tuple(result)

    def append(self, event: str, *, context_hash: str) -> None:
        lock = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            events = self.events()
            if len(events) >= len(_EVENT_ORDER) or event != _EVENT_ORDER[len(events)]:
                raise ValueError("selector invocation is out of order or repeated")
            if events and events[0]["context_hash"] != context_hash:
                raise ValueError("selector ledger context changed")
            body = {
                "schema_version": 1,
                "event": event,
                "ordinal": len(events),
                "context_hash": context_hash,
                "previous": events[-1]["event_hash"] if events else None,
            }
            encoded = canonical_json({**body, "event_hash": content_hash(body)}) + "\n"
            with self.path.open("ab") as stream:
                stream.write(encoded.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            self.events()
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)

    def receipt(self) -> dict:
        events = self.events()
        body = {
            "schema_version": 1,
            "event_count": len(events),
            "final_event": events[-1]["event"] if events else None,
            "ledger_bytes_hash": bytes_hash(self.path.read_bytes())
            if self.path.exists()
            else bytes_hash(b""),
            "selector_reservation_count": sum(
                item["event"] == "SELECTOR_RESERVED" for item in events
            ),
            "selector_invocation_count": sum(
                item["event"] == "SELECTOR_COMPLETED" for item in events
            ),
            "selector_rerun_count": max(
                0,
                sum(item["event"] == "SELECTOR_COMPLETED" for item in events) - 1,
            ),
        }
        return {**body, "receipt_hash": content_hash(body)}


def select_compilation_closed_sources_once(
    *,
    census: SelectableSourceCensus,
    closure_manifest: JavaCompilationClosureManifest,
    proof: JavaCompilationClosureFeasibilityProof,
    bindings: SourceEntryBindingManifest,
    selector_seed: str,
    ledger: M336FSelectorLedger,
    qualification_report_hash: str,
    qualification_summary_hash: str,
) -> tuple[M336FSelectedSourceManifest, M336FSelectorReceipt]:
    if any(
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in (qualification_report_hash, qualification_summary_hash)
    ):
        raise ValueError("selector qualification bindings must be SHA-256 hashes")
    verify_java_compilation_closure_feasibility_proof(proof, closure_manifest, census)
    verify_source_entry_binding_manifest(bindings)
    if not proof.hard_requirements_satisfied:
        raise ValueError("selector cannot run after an infeasible closure proof")
    decision_by_unit = {
        f"{item.candidate_root}/{item.canonical_path}": item
        for item in census.decisions
        if item.analysis_eligible
    }
    binding_by_unit = {
        item.selected_path: item
        for item in bindings.bindings
        if item.selected_path in decision_by_unit
    }
    if set(proof.witness_source_units) - set(binding_by_unit):
        raise ValueError("closure witness lacks SourceEntryId bindings")
    context_hash = content_hash(
        (
            qualification_report_hash,
            qualification_summary_hash,
            census.census_hash,
            closure_manifest.manifest_hash,
            proof.proof_hash,
            bindings.manifest_hash,
        )
    )
    ledger.append("CENSUS_SEALED", context_hash=context_hash)
    ledger.append("SELECTOR_RESERVED", context_hash=context_hash)
    rows = []
    dependency_owners = {
        edge.owner_source_unit_id
        for edge in closure_manifest.dependency_edges
        if edge.source_unit_id in proof.witness_source_units
        and edge.owner_source_unit_id in proof.witness_source_units
    }
    for unit in proof.witness_source_units:
        decision = decision_by_unit[unit]
        binding = binding_by_unit[unit]
        role = (
            "SELECTED_SEMANTIC_FILE"
            if decision.selectable
            else "SELECTED_CLOSURE_SUPPORT_FILE"
        )
        if unit in dependency_owners and not decision.selectable:
            role = "SELECTED_CLOSURE_SUPPORT_FILE"
        row_body = {
            "source_entry_identity_hash": binding.source_entry_id.identity_hash,
            "candidate_root": decision.candidate_root,
            "canonical_path": decision.canonical_path,
            "selected_path": binding.selected_path,
            "selection_role": role,
            "selection_rank": content_hash(
                (selector_seed, binding.source_entry_id.identity_hash, role)
            ),
        }
        rows.append(M336FSelectedSource(**row_body, row_hash=content_hash(row_body)))
    ordered = tuple(sorted(rows, key=lambda item: item.selected_path.encode("utf-8")))
    distribution = tuple(
        (root, sum(item.candidate_root == root for item in ordered))
        for root in sorted({item.candidate_root for item in ordered})
    )
    manifest_body = {
        "schema_version": 1,
        "qualification_report_hash": qualification_report_hash,
        "qualification_summary_hash": qualification_summary_hash,
        "census_hash": census.census_hash,
        "closure_manifest_hash": closure_manifest.manifest_hash,
        "feasibility_proof_hash": proof.proof_hash,
        "binding_manifest_hash": bindings.manifest_hash,
        "file_count": len(ordered),
        "root_count": len(distribution),
        "root_distribution": distribution,
        "semantic_file_count": sum(
            item.selection_role == "SELECTED_SEMANTIC_FILE" for item in ordered
        ),
        "closure_support_file_count": sum(
            item.selection_role == "SELECTED_CLOSURE_SUPPORT_FILE" for item in ordered
        ),
        "files": ordered,
    }
    manifest = M336FSelectedSourceManifest(
        **manifest_body, manifest_hash=content_hash(manifest_body)
    )
    ledger.append("SELECTOR_COMPLETED", context_hash=context_hash)
    counts = ledger.receipt()
    receipt_body = {
        "schema_version": 1,
        "selector_version": M336F_SELECTOR_VERSION,
        "selector_seed_hash": content_hash(selector_seed),
        "qualification_report_hash": qualification_report_hash,
        "qualification_summary_hash": qualification_summary_hash,
        "census_hash": census.census_hash,
        "closure_manifest_hash": closure_manifest.manifest_hash,
        "feasibility_proof_hash": proof.proof_hash,
        "binding_manifest_hash": bindings.manifest_hash,
        "selector_reservation_count": counts["selector_reservation_count"],
        "selector_invocation_count": counts["selector_invocation_count"],
        "selector_rerun_count": counts["selector_rerun_count"],
        "evaluator_read_count": 0,
        "golden_read_count": 0,
        "trust_metric_read_count": 0,
        "selected_manifest_hash": manifest.manifest_hash,
    }
    receipt = M336FSelectorReceipt(
        **receipt_body, receipt_hash=content_hash(receipt_body)
    )
    verify_m336f_selection(manifest, receipt, proof)
    return manifest, receipt


def verify_m336f_selection(manifest, receipt, proof) -> None:
    for row in manifest.files:
        body = asdict(row)
        claimed = body.pop("row_hash")
        if content_hash(body) != claimed:
            raise ValueError("selected source row hash mismatch")
    manifest_body = asdict(manifest)
    manifest_claim = manifest_body.pop("manifest_hash")
    receipt_body = asdict(receipt)
    receipt_claim = receipt_body.pop("receipt_hash")
    ordered = tuple(
        sorted(manifest.files, key=lambda item: item.selected_path.encode())
    )
    distribution = tuple(
        (root, sum(item.candidate_root == root for item in manifest.files))
        for root in sorted({item.candidate_root for item in manifest.files})
    )
    if (
        content_hash(manifest_body) != manifest_claim
        or content_hash(receipt_body) != receipt_claim
        or proof.hard_requirements_satisfied is not True
        or manifest.schema_version != 1
        or receipt.schema_version != 1
        or manifest.file_count != len(manifest.files)
        or manifest.files != ordered
        or len({item.selected_path for item in manifest.files}) != manifest.file_count
        or len({item.source_entry_identity_hash for item in manifest.files})
        != manifest.file_count
        or any(
            item.selected_path != f"{item.candidate_root}/{item.canonical_path}"
            or item.selection_role
            not in {"SELECTED_SEMANTIC_FILE", "SELECTED_CLOSURE_SUPPORT_FILE"}
            for item in manifest.files
        )
        or {item.selected_path for item in manifest.files}
        != set(proof.witness_source_units)
        or manifest.root_distribution != distribution
        or manifest.root_count != len(distribution)
        or manifest.semantic_file_count
        != sum(
            item.selection_role == "SELECTED_SEMANTIC_FILE" for item in manifest.files
        )
        or manifest.closure_support_file_count
        != sum(
            item.selection_role == "SELECTED_CLOSURE_SUPPORT_FILE"
            for item in manifest.files
        )
        or manifest.semantic_file_count + manifest.closure_support_file_count
        != manifest.file_count
        or manifest.file_count != proof.target_file_count
        or manifest.root_count < proof.minimum_root_count
        or max(count for _root, count in manifest.root_distribution)
        > proof.maximum_files_per_root
        or manifest.closure_manifest_hash != proof.closure_manifest_hash
        or manifest.feasibility_proof_hash != proof.proof_hash
        or receipt.selector_version != M336F_SELECTOR_VERSION
        or any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in (
                manifest.qualification_report_hash,
                manifest.qualification_summary_hash,
            )
        )
        or receipt.qualification_report_hash != manifest.qualification_report_hash
        or receipt.qualification_summary_hash != manifest.qualification_summary_hash
        or receipt.census_hash != manifest.census_hash
        or receipt.closure_manifest_hash != manifest.closure_manifest_hash
        or receipt.feasibility_proof_hash != manifest.feasibility_proof_hash
        or receipt.binding_manifest_hash != manifest.binding_manifest_hash
        or receipt.selector_reservation_count != 1
        or receipt.selector_invocation_count != 1
        or receipt.selector_rerun_count != 0
        or receipt.evaluator_read_count != 0
        or receipt.golden_read_count != 0
        or receipt.trust_metric_read_count != 0
        or receipt.selected_manifest_hash != manifest.manifest_hash
    ):
        raise ValueError("closure-aware selector invariants failed")


def m336f_selected_source_manifest_from_dict(value: dict):
    if set(value) != set(M336FSelectedSourceManifest.__dataclass_fields__):
        raise ValueError("selected source manifest schema changed")
    result = M336FSelectedSourceManifest(
        **{
            **value,
            "root_distribution": tuple(
                tuple(item) for item in value["root_distribution"]
            ),
            "files": tuple(M336FSelectedSource(**item) for item in value["files"]),
        }
    )
    return result


def m336f_selector_receipt_from_dict(value: dict):
    if set(value) != set(M336FSelectorReceipt.__dataclass_fields__):
        raise ValueError("selector receipt schema changed")
    return M336FSelectorReceipt(**value)
