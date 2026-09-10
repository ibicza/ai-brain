"""Typed, count-neutral protocol primitives for the M-33.6k.2 final route.

This module deliberately contains no candidate-specific acceptance rules.  It is
the common protocol used by rehearsal and final execution: only the authority,
run identifiers, and private destinations differ between those modes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

M336K2_BRANCH = "exp/stage3-m336k2-final-java-outcome-a-v12"
M336K2_BRANCH_REF = f"refs/heads/{M336K2_BRANCH}"
M336K2_R28_SUBJECT = "M-33.6k.2 close candidate-isolated final Java route"
M336K2_Q28_SUBJECT = "M-33.6k.2 qualify final Java route"
M336K2_F28_SUBJECT = "M-33.6k.2 freeze final Java execution"
M336K2_H28_SUBJECT = "M-33.6k.2 publish sealed Java production"
M336K2_E28_SUBJECT = "M-33.6k.2 publish independent Java evidence"
M336K2_READY_STATUS = "READY_FOR_CANDIDATE_ISOLATED_FINAL_JAVA_EXECUTION_V3"

M336K2_ROUTE_EVENTS = (
    "PREFLIGHT_VERIFIED",
    "FREEZE_VERIFIED",
    "AUTHORIZATION_VALIDATED",
    "ACQUISITION_RESERVED",
    "ACQUISITION_STARTED",
    "ALL_CANDIDATES_TERMINAL",
    "ACQUISITION_COMPLETED",
    "VAULT_SEALED",
    "KARINA_VAULT_VERIFIED",
    "QUALIFICATION_COMPLETED",
    "SELECTOR_RESERVED",
    "SELECTOR_INVOKED",
    "SELECTOR_COMPLETED",
    "SELECTED_SNAPSHOT_SEALED",
    "WINDOWS_PRODUCTION_SEALED",
    "KARINA_PRODUCTION_SEALED",
    "PRODUCTION_COMPARISON_PASSED",
    "H_PUBLICATION_READY",
    "EVALUATOR_RESERVED",
    "GOLDENS_CREATED",
    "WINDOWS_EVALUATION_COMPLETED",
    "KARINA_EVALUATION_COMPLETED",
    "EVALUATION_COMPARISON_PASSED",
    "RUNTIME_COMPLETED",
    "E_PUBLICATION_READY",
    "FINAL_VERIFICATION_COMPLETED",
)
M336K2_TERMINAL_FAILURE = "FINAL_ROUTE_FAILED"

M336K2_REQUIRED_FREEZE_COMPONENTS = frozenset(
    {
        "implementation_tip",
        "q28_commit",
        "f28_commit",
        "committed_f28_tree",
        "q28_evidence_manifest",
        "q28_readiness",
        "final_authorization",
        "freeze_manifest",
        "frozen_file_manifest",
        "route_registry",
        "route_manifest",
        "schema_registry",
        "execution_capsule_receipt",
        "python_environment_manifest",
        "executable_dependency_manifest",
        "windows_jdk_identity",
        "karina_jdk_identity",
        "karina_stable_host_identity",
        "candidate_pool",
        "acquisition_policy",
        "archive_policy",
        "candidate_terminal_policy",
        "global_continuation_policy",
        "selector_policy",
        "threshold_manifest",
        "disclosure_registry_manifest",
        "denylist",
        "publication_boundary",
        "public_pack_contract",
        "h28_publication_contract",
        "e28_publication_contract",
        "commit_protocol",
        "storage_budget",
    }
)

_HASH = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class M336K2ProtocolError(ValueError):
    """A final-route contract failed closed."""


class M336K2MutationLayer(str, Enum):
    ARCHIVE = "ARCHIVE_INSPECTION"
    CANDIDATE = "CANDIDATE_ISOLATION"
    FREEZE = "FREEZE_AND_ROUTE"
    ORDERING = "LEDGER_ORDERING"
    PUBLICATION = "PUBLICATION_BOUNDARY"


M336K2_MUTATION_MATRIX = {
    # Archive behavior.
    "ordinary_archive": M336K2MutationLayer.ARCHIVE,
    "duplicate_identical_directory": M336K2MutationLayer.ARCHIVE,
    "duplicate_directory_metadata_conflict": M336K2MutationLayer.ARCHIVE,
    "duplicate_identical_regular_file": M336K2MutationLayer.ARCHIVE,
    "duplicate_conflicting_regular_file": M336K2MutationLayer.ARCHIVE,
    "file_directory_conflict": M336K2MutationLayer.ARCHIVE,
    "nfc_collision": M336K2MutationLayer.ARCHIVE,
    "casefold_collision": M336K2MutationLayer.ARCHIVE,
    "separator_alias": M336K2MutationLayer.ARCHIVE,
    "traversal": M336K2MutationLayer.ARCHIVE,
    "absolute_path": M336K2MutationLayer.ARCHIVE,
    "drive_path": M336K2MutationLayer.ARCHIVE,
    "unc_path": M336K2MutationLayer.ARCHIVE,
    "symlink": M336K2MutationLayer.ARCHIVE,
    "encryption": M336K2MutationLayer.ARCHIVE,
    "unknown_entry_kind": M336K2MutationLayer.ARCHIVE,
    "malformed_central_directory": M336K2MutationLayer.ARCHIVE,
    "unreadable_payload": M336K2MutationLayer.ARCHIVE,
    "size_limit": M336K2MutationLayer.ARCHIVE,
    "compression_ratio_limit": M336K2MutationLayer.ARCHIVE,
    "license_conflict": M336K2MutationLayer.ARCHIVE,
    # Candidate isolation.
    "failure_first_candidate": M336K2MutationLayer.CANDIDATE,
    "failure_middle_candidate": M336K2MutationLayer.CANDIDATE,
    "failure_last_candidate": M336K2MutationLayer.CANDIDATE,
    "consecutive_failures": M336K2MutationLayer.CANDIDATE,
    "alternating_failures": M336K2MutationLayer.CANDIDATE,
    "rejection_10_percent": M336K2MutationLayer.CANDIDATE,
    "rejection_25_percent": M336K2MutationLayer.CANDIDATE,
    "rejection_50_percent": M336K2MutationLayer.CANDIDATE,
    "all_but_three_rejected": M336K2MutationLayer.CANDIDATE,
    "all_candidates_rejected": M336K2MutationLayer.CANDIDATE,
    "optional_source_fetch_failure": M336K2MutationLayer.CANDIDATE,
    "optional_pom_failure": M336K2MutationLayer.CANDIDATE,
    "optional_scm_failure": M336K2MutationLayer.CANDIDATE,
    "metadata_drift": M336K2MutationLayer.CANDIDATE,
    "correspondence_failure": M336K2MutationLayer.CANDIDATE,
    "candidate_license_failure": M336K2MutationLayer.CANDIDATE,
    "unknown_programming_exception": M336K2MutationLayer.CANDIDATE,
    "missing_terminal_receipt": M336K2MutationLayer.CANDIDATE,
    "duplicate_terminal_receipt": M336K2MutationLayer.CANDIDATE,
    # Freeze and route.
    "wrong_q_sha": M336K2MutationLayer.FREEZE,
    "wrong_f_sha": M336K2MutationLayer.FREEZE,
    "wrong_committed_tree": M336K2MutationLayer.FREEZE,
    "wrong_route_component_hash": M336K2MutationLayer.FREEZE,
    "wrong_environment": M336K2MutationLayer.FREEZE,
    "wrong_git": M336K2MutationLayer.FREEZE,
    "bare_executable": M336K2MutationLayer.FREEZE,
    "wrong_jdk": M336K2MutationLayer.FREEZE,
    "wrong_host_key": M336K2MutationLayer.FREEZE,
    "dirty_worktree": M336K2MutationLayer.FREEZE,
    "wrong_upstream": M336K2MutationLayer.FREEZE,
    "wrong_branch": M336K2MutationLayer.FREEZE,
    "merge_ancestry": M336K2MutationLayer.FREEZE,
    "stale_readiness": M336K2MutationLayer.FREEZE,
    "preexisting_acquisition_ledger": M336K2MutationLayer.FREEZE,
    "preexisting_vault": M336K2MutationLayer.FREEZE,
    "preexisting_selector_evaluator_state": M336K2MutationLayer.FREEZE,
    "insufficient_storage": M336K2MutationLayer.FREEZE,
    # Ordering.
    "selector_before_acquisition_completion": M336K2MutationLayer.ORDERING,
    "second_selector_reservation": M336K2MutationLayer.ORDERING,
    "evaluator_before_both_production_seals": M336K2MutationLayer.ORDERING,
    "golden_before_evaluator_reservation": M336K2MutationLayer.ORDERING,
    "second_evaluator_reservation": M336K2MutationLayer.ORDERING,
    "retry_after_worker_crash": M336K2MutationLayer.ORDERING,
    "h_before_both_production_seals": M336K2MutationLayer.ORDERING,
    "e_before_evaluation_completion": M336K2MutationLayer.ORDERING,
    # Publication.
    "raw_source": M336K2MutationLayer.PUBLICATION,
    "source_window_256": M336K2MutationLayer.PUBLICATION,
    "base64_source": M336K2MutationLayer.PUBLICATION,
    "hex_source": M336K2MutationLayer.PUBLICATION,
    "source_archive": M336K2MutationLayer.PUBLICATION,
    "absolute_host_path": M336K2MutationLayer.PUBLICATION,
    "private_manifest": M336K2MutationLayer.PUBLICATION,
    "uncontracted_json": M336K2MutationLayer.PUBLICATION,
    "modified_h_pack_during_e": M336K2MutationLayer.PUBLICATION,
    "wrong_h_e_parent": M336K2MutationLayer.PUBLICATION,
    "wrong_subject": M336K2MutationLayer.PUBLICATION,
    "unauthorized_path": M336K2MutationLayer.PUBLICATION,
}


def verify_mutation_rejected_at_layer(
    mutation: str, rejected_layer: M336K2MutationLayer
) -> None:
    expected = M336K2_MUTATION_MATRIX.get(mutation)
    if expected is None:
        raise M336K2ProtocolError("M336K2 mutation is not registered")
    if rejected_layer != expected:
        raise M336K2ProtocolError(
            f"M336K2 mutation rejected at wrong layer: {mutation}"
        )


@dataclass(frozen=True)
class M336K2RouteEvent:
    schema_version: int
    ordinal: int
    event: str
    context_hash: str
    operation_hash: str
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class M336K2RouteLedgerReceipt:
    schema_version: int
    event_count: int
    final_event: str | None
    event_counts: tuple[tuple[str, int], ...]
    acquisition_reservation_count: int
    acquisition_invocation_count: int
    selector_reservation_count: int
    selector_invocation_count: int
    evaluator_reservation_count: int
    evaluator_invocation_count: int
    retry_count: int
    ledger_bytes_hash: str
    receipt_hash: str


class M336K2RouteLedger:
    """Append-only, fsync-backed ledger enforcing the exact final route order."""

    def __init__(self, path: Path, *, git_worktrees: Iterable[Path] = ()) -> None:
        self.path = path.resolve(strict=False)
        for worktree in git_worktrees:
            if _is_relative_to(self.path, worktree.resolve(strict=True)):
                raise M336K2ProtocolError("M336K2 route ledger must remain outside Git")
        if self.path.exists():
            self.events()

    def events(self) -> tuple[M336K2RouteEvent, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if b"\r" in raw or (raw and not raw.endswith(b"\n")):
            raise M336K2ProtocolError("M336K2 route ledger is not canonical LF JSONL")
        events: list[M336K2RouteEvent] = []
        previous = None
        for index, line in enumerate(raw.splitlines(), start=1):
            value = _strict_object(line)
            if set(value) != set(M336K2RouteEvent.__dataclass_fields__):
                raise M336K2ProtocolError("M336K2 route event fields changed")
            event = M336K2RouteEvent(**value)
            body = asdict(event)
            claimed = body.pop("event_hash")
            if (
                event.schema_version != 1
                or event.ordinal != index
                or event.previous_event_hash != previous
                or not _HASH.fullmatch(event.context_hash)
                or not _HASH.fullmatch(event.operation_hash)
                or content_hash(body) != claimed
            ):
                raise M336K2ProtocolError("M336K2 route ledger hash chain is invalid")
            events.append(event)
            previous = event.event_hash
        _verify_route_order(tuple(item.event for item in events))
        return tuple(events)

    def append(self, event: str, *, context_hash: str, operation_hash: str) -> None:
        events = self.events()
        names = tuple(item.event for item in events)
        if names and names[-1] in {M336K2_TERMINAL_FAILURE, M336K2_ROUTE_EVENTS[-1]}:
            raise M336K2ProtocolError("M336K2 route ledger is terminal")
        expected = (
            M336K2_ROUTE_EVENTS[len(names)]
            if len(names) < len(M336K2_ROUTE_EVENTS)
            else None
        )
        if event != expected:
            raise M336K2ProtocolError(
                f"M336K2 route event out of order: expected {expected}, got {event}"
            )
        self._append(event, context_hash=context_hash, operation_hash=operation_hash)

    def fail(self, *, context_hash: str, operation_hash: str) -> None:
        events = self.events()
        if not events or events[-1].event in {
            M336K2_TERMINAL_FAILURE,
            M336K2_ROUTE_EVENTS[-1],
        }:
            raise M336K2ProtocolError("M336K2 route failure transition is invalid")
        self._append(
            M336K2_TERMINAL_FAILURE,
            context_hash=context_hash,
            operation_hash=operation_hash,
        )

    def _append(self, event: str, *, context_hash: str, operation_hash: str) -> None:
        if not _HASH.fullmatch(context_hash) or not _HASH.fullmatch(operation_hash):
            raise M336K2ProtocolError("M336K2 route event hashes are invalid")
        events = self.events()
        body = {
            "schema_version": 1,
            "ordinal": len(events) + 1,
            "event": event,
            "context_hash": context_hash,
            "operation_hash": operation_hash,
            "previous_event_hash": events[-1].event_hash if events else None,
        }
        value = {**body, "event_hash": content_hash(body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            os.write(fd, (canonical_json(value) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        self.events()

    def receipt(self) -> M336K2RouteLedgerReceipt:
        events = self.events()
        counts = Counter(item.event for item in events)
        body = {
            "schema_version": 1,
            "event_count": len(events),
            "final_event": events[-1].event if events else None,
            "event_counts": tuple(sorted(counts.items())),
            "acquisition_reservation_count": counts["ACQUISITION_RESERVED"],
            "acquisition_invocation_count": counts["ACQUISITION_STARTED"],
            "selector_reservation_count": counts["SELECTOR_RESERVED"],
            "selector_invocation_count": counts["SELECTOR_INVOKED"],
            "evaluator_reservation_count": counts["EVALUATOR_RESERVED"],
            "evaluator_invocation_count": min(
                counts["WINDOWS_EVALUATION_COMPLETED"],
                counts["KARINA_EVALUATION_COMPLETED"],
            ),
            "retry_count": 0,
            "ledger_bytes_hash": (
                bytes_hash(self.path.read_bytes())
                if self.path.exists()
                else bytes_hash(b"")
            ),
        }
        return M336K2RouteLedgerReceipt(**body, receipt_hash=content_hash(body))


@dataclass(frozen=True)
class M336K2ExecutableBinding:
    schema_version: int
    role: str
    path_identity_hash: str
    file_sha256: str
    semantic_version: str
    semantic_version_hash: str
    binding_hash: str


def build_executable_binding(
    path: Path, *, role: str, version_arguments: tuple[str, ...]
) -> M336K2ExecutableBinding:
    """Bind an explicit executable without publishing its private path."""

    if not path.is_absolute():
        raise M336K2ProtocolError(f"bare executable forbidden for {role}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise M336K2ProtocolError(f"executable is not a file for {role}")
    result = subprocess.run(
        (str(resolved), *version_arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    )
    version = (result.stdout + result.stderr).strip()
    if not version:
        raise M336K2ProtocolError(f"executable version is empty for {role}")
    body = {
        "schema_version": 1,
        "role": role,
        "path_identity_hash": content_hash(resolved.as_posix()),
        "file_sha256": bytes_hash(resolved.read_bytes()),
        "semantic_version": version,
        "semantic_version_hash": content_hash(version),
    }
    return M336K2ExecutableBinding(**body, binding_hash=content_hash(body))


def verify_executable_binding(path: Path, binding: M336K2ExecutableBinding) -> None:
    rebuilt = build_executable_binding(
        path,
        role=binding.role,
        version_arguments=_version_arguments(binding.role),
    )
    if rebuilt != binding:
        raise M336K2ProtocolError(f"executable binding changed for {binding.role}")


@dataclass(frozen=True)
class M336K2ReadinessState:
    schema_version: int
    acquisition_reservations: int
    acquisition_invocations: int
    selector_reservations: int
    selector_invocations: int
    evaluator_reservations: int
    evaluator_invocations: int
    route_state_events: int
    final_candidate_source_body_bytes: int
    absent_destination_count: int
    destination_count: int
    status: str
    readiness_hash: str


def build_unspent_readiness_state(
    destinations: Mapping[str, Path],
) -> M336K2ReadinessState:
    required = {
        "acquisition_ledger",
        "selector_ledger",
        "evaluator_ledger",
        "route_state_ledger",
        "vault",
        "selected_source_snapshot",
        "windows_production",
        "karina_production",
        "evaluator_root",
    }
    if set(destinations) != required:
        raise M336K2ProtocolError("M336K2 readiness destination fields changed")
    existing = tuple(name for name, path in destinations.items() if path.exists())
    body = {
        "schema_version": 1,
        "acquisition_reservations": 0,
        "acquisition_invocations": 0,
        "selector_reservations": 0,
        "selector_invocations": 0,
        "evaluator_reservations": 0,
        "evaluator_invocations": 0,
        "route_state_events": 0,
        "final_candidate_source_body_bytes": 0,
        "absent_destination_count": len(destinations) - len(existing),
        "destination_count": len(destinations),
        "status": M336K2_READY_STATUS if not existing else "BLOCKED",
    }
    value = M336K2ReadinessState(**body, readiness_hash=content_hash(body))
    if existing:
        raise M336K2ProtocolError(
            "M336K2 final state is already spent or destinations are stale"
        )
    return value


@dataclass(frozen=True)
class M336K2FrozenComponent:
    name: str
    relative_path: str
    bytes_hash: str
    byte_count: int


@dataclass(frozen=True)
class M336K2FreezeManifest:
    schema_version: int
    contract_role: str
    implementation_tip: str
    exact_q28_sha: str
    exact_f28_sha: str
    committed_f28_tree: str
    readiness_hash: str
    authorization_hash: str
    route_hash: str
    components: tuple[M336K2FrozenComponent, ...]
    self_reference_safe_exclusions: tuple[str, ...]
    prospective_freeze_tree_hash: str
    manifest_hash: str


def verify_complete_freeze(
    root: Path,
    manifest: M336K2FreezeManifest,
    *,
    allow_prospective_f28: bool = False,
) -> None:
    """Verify the complete frozen component closure before any ledger write."""

    if manifest.schema_version != 1 or manifest.contract_role != "M336K2_F28_FREEZE":
        raise M336K2ProtocolError("M336K2 freeze role/schema changed")
    names = {item.name for item in manifest.components}
    if names != M336K2_REQUIRED_FREEZE_COMPONENTS:
        missing = M336K2_REQUIRED_FREEZE_COMPONENTS - names
        extra = names - M336K2_REQUIRED_FREEZE_COMPONENTS
        raise M336K2ProtocolError(
            f"M336K2 frozen component set changed: missing={len(missing)} extra={len(extra)}"
        )
    if len(names) != len(manifest.components):
        raise M336K2ProtocolError("M336K2 frozen component is duplicated")
    for item in manifest.components:
        if not _safe_relative(item.relative_path):
            raise M336K2ProtocolError("M336K2 frozen component path is unsafe")
        path = root.joinpath(*item.relative_path.split("/"))
        if (
            not path.is_file()
            or path.stat().st_size != item.byte_count
            or bytes_hash(path.read_bytes()) != item.bytes_hash
        ):
            raise M336K2ProtocolError(f"M336K2 frozen component changed: {item.name}")
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K2 freeze manifest hash changed")
    shas = (manifest.implementation_tip, manifest.exact_q28_sha)
    if not all(_SHA.fullmatch(item) for item in shas):
        raise M336K2ProtocolError("M336K2 freeze commit binding is invalid")
    f28_is_zero = manifest.exact_f28_sha == "0" * 40
    tree_is_zero = manifest.committed_f28_tree == "0" * 40
    if allow_prospective_f28:
        if f28_is_zero != tree_is_zero:
            raise M336K2ProtocolError("M336K2 prospective F28 binding is inconsistent")
    elif f28_is_zero or tree_is_zero:
        raise M336K2ProtocolError("M336K2 committed F28 binding is absent")


@dataclass(frozen=True)
class M336K2CommittedFreezeAttestation:
    schema_version: int
    exact_f28_sha: str
    exact_q28_parent: str
    committed_tree_hash: str
    prospective_freeze_tree_hash: str
    prospective_tree_matches: bool
    self_reference_safe_exclusions: tuple[str, ...]
    authorization_hash: str
    route_hash: str
    implementation_change_count: int
    merge_count: int
    head_upstream_remote_equal: bool
    worktree_clean: bool
    status: str
    attestation_hash: str


def attest_committed_f28(
    repository: Path,
    git_executable: Path,
    *,
    freeze_manifest: M336K2FreezeManifest,
    exact_f28_sha: str,
) -> M336K2CommittedFreezeAttestation:
    git = git_executable.resolve(strict=True)
    root = repository.resolve(strict=True)
    verify_complete_freeze(root, freeze_manifest, allow_prospective_f28=True)
    implementation_tip = freeze_manifest.implementation_tip
    exact_q28_sha = freeze_manifest.exact_q28_sha
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    parent = _git(git, root, "rev-parse", f"{exact_f28_sha}^")
    tree = _git(git, root, "rev-parse", f"{exact_f28_sha}^{{tree}}")
    branch = _git(git, root, "symbolic-ref", "--short", "HEAD")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()[0]
    dirty = _git(git, root, "status", "--porcelain=v1")
    merges = int(
        _git(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{implementation_tip}..{exact_f28_sha}",
        )
    )
    implementation_changes = tuple(
        line
        for line in _git(
            git,
            root,
            "diff",
            "--name-only",
            implementation_tip,
            exact_f28_sha,
            "--",
            "src",
            "scripts",
            "tools",
            "tests",
            "schemas",
        ).splitlines()
        if line
    )
    prospective = _committed_prospective_identity(
        git,
        root,
        exact_f28_sha,
        freeze_manifest.self_reference_safe_exclusions,
    )
    passed = (
        head == exact_f28_sha
        and parent == exact_q28_sha
        and head == upstream == remote
        and not dirty
        and not merges
        and not implementation_changes
        and prospective == freeze_manifest.prospective_freeze_tree_hash
    )
    body = {
        "schema_version": 1,
        "exact_f28_sha": exact_f28_sha,
        "exact_q28_parent": parent,
        "committed_tree_hash": tree,
        "prospective_freeze_tree_hash": freeze_manifest.prospective_freeze_tree_hash,
        "prospective_tree_matches": (
            prospective == freeze_manifest.prospective_freeze_tree_hash
        ),
        "self_reference_safe_exclusions": (
            freeze_manifest.self_reference_safe_exclusions
        ),
        "authorization_hash": freeze_manifest.authorization_hash,
        "route_hash": freeze_manifest.route_hash,
        "implementation_change_count": len(implementation_changes),
        "merge_count": merges,
        "head_upstream_remote_equal": head == upstream == remote,
        "worktree_clean": not dirty,
        "status": "PASS" if passed else "FAIL",
    }
    result = M336K2CommittedFreezeAttestation(
        **body, attestation_hash=content_hash(body)
    )
    if not passed:
        raise M336K2ProtocolError("M336K2 committed F28 attestation failed")
    return result


def validate_count_neutral_pool(
    candidates: Iterable[Mapping[str, object]],
    *,
    minimum_families: int,
    minimum_organizations: int,
    maximum_per_organization: int,
) -> dict:
    rows = tuple(candidates)
    families = {item.get("family_id") for item in rows}
    organizations = Counter(item.get("organization_id") for item in rows)
    passed = (
        len(rows) == len(families)
        and len(families) >= minimum_families
        and len(organizations) >= minimum_organizations
        and max(organizations.values(), default=0) <= maximum_per_organization
        and all(item.get("requirement") == "OPTIONAL" for item in rows)
    )
    body = {
        "schema_version": 1,
        "candidate_family_count": len(families),
        "organization_count": len(organizations),
        "maximum_candidates_per_organization": max(organizations.values(), default=0),
        "minimum_candidate_family_threshold": minimum_families,
        "minimum_organization_threshold": minimum_organizations,
        "maximum_per_organization_threshold": maximum_per_organization,
        "all_candidates_optional": all(
            item.get("requirement") == "OPTIONAL" for item in rows
        ),
        "status": "PASS" if passed else "FAIL",
    }
    if not passed:
        raise M336K2ProtocolError("M336K2 candidate pool diversity failed")
    return {**body, "receipt_hash": content_hash(body)}


def _verify_route_order(names: tuple[str, ...]) -> None:
    if M336K2_TERMINAL_FAILURE in names:
        failure = names.index(M336K2_TERMINAL_FAILURE)
        if (
            failure != len(names) - 1
            or names[:failure] != M336K2_ROUTE_EVENTS[:failure]
        ):
            raise M336K2ProtocolError("M336K2 terminal failure order is invalid")
        return
    if names != M336K2_ROUTE_EVENTS[: len(names)]:
        raise M336K2ProtocolError("M336K2 route event order is invalid")


def _strict_object(raw: bytes) -> dict:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise M336K2ProtocolError("M336K2 JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 JSON is malformed") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 JSON value is not an object")
    return value


def _git(git: Path, repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()


def _committed_prospective_identity(
    git: Path,
    repository: Path,
    exact_f28_sha: str,
    exclusions: tuple[str, ...],
) -> str:
    if not exclusions or any(not _safe_relative(item) for item in exclusions):
        raise M336K2ProtocolError("M336K2 F28 self-reference exclusions are invalid")
    roots = {str(Path(item).parent).replace("\\", "/") for item in exclusions}
    if len(roots) != 1:
        raise M336K2ProtocolError("M336K2 F28 exclusions do not share one root")
    freeze_root = roots.pop()
    raw = subprocess.run(
        (
            str(git),
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            exact_f28_sha,
            "--",
            freeze_root,
        ),
        cwd=repository,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout
    paths = tuple(
        item.decode("utf-8")
        for item in raw.split(b"\0")
        if item and item.decode("utf-8") not in exclusions
    )
    rows = []
    for path in sorted(paths, key=lambda item: item.encode("utf-8")):
        blob = subprocess.run(
            (str(git), "show", f"{exact_f28_sha}:{path}"),
            cwd=repository,
            check=True,
            capture_output=True,
            env=m336k2_minimal_environment(),
        ).stdout
        relative = Path(path).relative_to(Path(freeze_root)).as_posix()
        rows.append((relative, len(blob), bytes_hash(blob)))
    return content_hash(tuple(rows))


def m336k2_minimal_environment() -> dict[str, str]:
    allowed = (
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    )
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    result.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": "",
            "PIP_NO_INDEX": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TZ": "UTC",
            "UV_OFFLINE": "1",
        }
    )
    return result


def _version_arguments(role: str) -> tuple[str, ...]:
    role = role.casefold().removeprefix("karina_")
    if role in {"java", "javac"}:
        return ("-version",)
    if role in {"ssh", "scp"}:
        return ("-V",)
    if role == "powershell":
        return (
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$PSVersionTable.PSVersion.ToString()",
        )
    if role == "cmd":
        return ("/d", "/c", "ver")
    return ("--version",)


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return (
        isinstance(value, str)
        and value == path.as_posix()
        and not path.is_absolute()
        and value not in {"", "."}
        and ".." not in path.parts
        and "\\" not in value
        and not re.match(r"^[A-Za-z]:", value)
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
