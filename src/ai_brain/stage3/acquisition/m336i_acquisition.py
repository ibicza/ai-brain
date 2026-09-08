"""Authorized, one-shot M-33.6i Java source acquisition."""

from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    FreshAcquisitionPreflight,
    run_fresh_acquisition_and_preflight,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)

M336I_FINAL_ACQUISITION_RUN_ID = "m336i.final-java.global-acquisition.v1"
M336I_ACQUISITION_EVENTS = (
    "AUTHORIZATION_VALIDATED",
    "ACQUISITION_RESERVED",
    "ACQUISITION_STARTED",
    "ACQUISITION_COMPLETED",
)
M336I_FROZEN_AUTHORIZATION_ROLE = "FROZEN_FINAL_ACQUISITION_AUTHORIZATION"
M336I_FREEZE_IDENTITY_EXCLUSIONS = frozenset(
    {
        "artifacts/acquisition/m336i_freeze_v8/final_acquisition_authorization.json",
        "artifacts/acquisition/m336i_freeze_v8/freeze_manifest.json",
    }
)
M336I_FROZEN_AUTHORIZATION_PATH = next(
    item
    for item in M336I_FREEZE_IDENTITY_EXCLUSIONS
    if item.endswith("final_acquisition_authorization.json")
)
M336I_FREEZE_MANIFEST_PATH = next(
    item
    for item in M336I_FREEZE_IDENTITY_EXCLUSIONS
    if item.endswith("freeze_manifest.json")
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class M336IFinalAcquisitionAuthorization:
    schema_version: int
    authorization_role: str
    acquisition_mode: str
    exact_q23_sha: str
    r24_implementation_tree_identity: str
    q24_evidence_identity: str
    f24_parent_sha: str
    f24_freeze_tree_identity: str
    route_registry_hash: str
    route_manifest_hash: str
    acquisition_provider_source_hash: str
    acquisition_provider_callable_signature_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    denylist_hash: str
    authority_root_hash: str
    selector_policy_hash: str
    threshold_manifest_hash: str
    publication_boundary_hash: str
    public_artifact_contract_hash: str
    windows_public_jdk_identity_receipt_hash: str
    karina_public_jdk_identity_receipt_hash: str
    karina_stable_host_identity_receipt_hash: str
    acquisition_run_id: str
    allowed_network_hosts: tuple[str, ...]
    expected_global_acquisition_count: int
    expected_windows_acquisition_count: int
    expected_karina_acquisition_count: int
    branch_ref: str
    authorization_hash: str


@dataclass(frozen=True)
class M336IFinalAcquisitionRequest:
    repository: Path
    supplied_f24_sha: str
    authorization: M336IFinalAcquisitionAuthorization
    candidate_pool: Path
    acquisition_policy: Path
    denylist: Path
    authority_root: Path
    authority_statement: Path
    frozen_route_registry: Path
    frozen_route_manifest: Path
    selector_policy: Path
    threshold_manifest: Path
    publication_boundary_contract: Path
    public_artifact_contract: Path
    compiler_jdk_identities: Path
    karina_host_identity_receipt: Path
    acquisition_ledger: Path
    vault_destination: Path
    private_acquisition_output: Path
    public_receipt_output: Path
    public_staging_root: Path
    unused_selected_source_output: Path
    platform_role: str


@dataclass(frozen=True)
class M336IFinalAcquisitionReceipt:
    schema_version: int
    contract_role: str
    acquisition_mode: str
    exact_f24_sha: str
    authorization_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    acquired_candidate_count: int
    failed_candidate_count: int
    vault_file_count: int
    java_file_count: int
    portable_vault_tree_hash: str
    portable_vault_manifest_hash: str
    legal_document_count: int
    unknown_legal_document_role_count: int
    network_host_counts: tuple[tuple[str, int], ...]
    global_acquisition_reservation_count: int
    global_acquisition_invocation_count: int
    windows_acquisition_invocation_count: int
    karina_acquisition_invocation_count: int
    acquisition_rerun_count: int
    replacement_candidate_count: int
    qualification_report_hash: str
    source_entry_binding_manifest_hash: str
    selectability_census_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336IAcquisitionLedgerEvent:
    schema_version: int
    event: str
    ordinal: int
    context_hash: str
    operation_hash: str
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class M336IAcquisitionLedgerReceipt:
    schema_version: int
    context_hash: str | None
    event_count: int
    final_event: str | None
    final_event_hash: str | None
    ledger_bytes_hash: str
    authorization_validation_count: int
    acquisition_reservation_count: int
    acquisition_start_count: int
    acquisition_completion_count: int
    acquisition_failure_count: int
    acquisition_rerun_count: int
    blocked: bool
    receipt_hash: str


class M336IAcquisitionCrash(RuntimeError):
    """Deterministic crash injection used by executable recovery tests."""


class M336IFinalAcquisitionLedger:
    """Canonical fsync-backed one-shot acquisition ledger."""

    def __init__(self, path: Path, *, git_worktrees=()):
        self.path = path.resolve(strict=False)
        roots = tuple(Path(item).resolve(strict=True) for item in git_worktrees)
        if any(_is_relative_to(self.path, root) for root in roots):
            raise ValueError("M336I acquisition ledger must remain outside Git")

    def events(self) -> tuple[M336IAcquisitionLedgerEvent, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if raw and (b"\r" in raw or not raw.endswith(b"\n")):
            raise ValueError("M336I acquisition ledger is not canonical LF JSONL")
        result = []
        previous = None
        context = None
        for ordinal, line in enumerate(raw.splitlines()):
            value = _strict_json_bytes(line)
            if set(value) != set(M336IAcquisitionLedgerEvent.__dataclass_fields__):
                raise ValueError("M336I acquisition event fields changed")
            event = M336IAcquisitionLedgerEvent(**value)
            body = asdict(event)
            claimed = body.pop("event_hash")
            if (
                event.schema_version != 1
                or event.ordinal != ordinal
                or event.previous_event_hash != previous
                or _SHA256.fullmatch(event.context_hash) is None
                or _SHA256.fullmatch(event.operation_hash) is None
                or content_hash(body) != claimed
            ):
                raise ValueError("M336I acquisition ledger hash chain is invalid")
            if context is None:
                context = event.context_hash
            elif context != event.context_hash:
                raise ValueError("M336I acquisition ledger context changed")
            result.append(event)
            previous = event.event_hash
        _verify_acquisition_event_order(tuple(result))
        return tuple(result)

    def append(self, event: str, *, context_hash: str, operation_hash: str) -> None:
        if (
            _SHA256.fullmatch(context_hash) is None
            or _SHA256.fullmatch(operation_hash) is None
        ):
            raise ValueError("M336I acquisition event requires SHA-256 bindings")
        lock = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, b"M336I_ACQUISITION_LOCK\n")
            os.fsync(descriptor)
            prior = self.events()
            if prior and prior[-1].event in {
                "ACQUISITION_COMPLETED",
                "ACQUISITION_FAILED",
            }:
                raise ValueError("M336I acquisition ledger is terminal")
            expected = M336I_ACQUISITION_EVENTS[len(prior)]
            if event == "ACQUISITION_FAILED":
                if not prior or prior[-1].event not in {
                    "ACQUISITION_RESERVED",
                    "ACQUISITION_STARTED",
                }:
                    raise ValueError("M336I acquisition failure boundary is invalid")
            elif event != expected:
                raise ValueError("M336I acquisition event is out of order or repeated")
            if prior and prior[0].context_hash != context_hash:
                raise ValueError("M336I acquisition context changed")
            body = {
                "schema_version": 1,
                "event": event,
                "ordinal": len(prior),
                "context_hash": context_hash,
                "operation_hash": operation_hash,
                "previous_event_hash": prior[-1].event_hash if prior else None,
            }
            encoded = (
                canonical_json({**body, "event_hash": content_hash(body)}) + "\n"
            ).encode()
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self.events()
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)

    def receipt(self) -> M336IAcquisitionLedgerReceipt:
        events = self.events()
        counts = {
            name: sum(item.event == name for item in events)
            for name in (*M336I_ACQUISITION_EVENTS, "ACQUISITION_FAILED")
        }
        body = {
            "schema_version": 1,
            "context_hash": events[0].context_hash if events else None,
            "event_count": len(events),
            "final_event": events[-1].event if events else None,
            "final_event_hash": events[-1].event_hash if events else None,
            "ledger_bytes_hash": bytes_hash(self.path.read_bytes())
            if self.path.exists()
            else bytes_hash(b""),
            "authorization_validation_count": counts["AUTHORIZATION_VALIDATED"],
            "acquisition_reservation_count": counts["ACQUISITION_RESERVED"],
            "acquisition_start_count": counts["ACQUISITION_STARTED"],
            "acquisition_completion_count": counts["ACQUISITION_COMPLETED"],
            "acquisition_failure_count": counts["ACQUISITION_FAILED"],
            "acquisition_rerun_count": max(0, counts["ACQUISITION_STARTED"] - 1),
            "blocked": bool(events) and events[-1].event != "ACQUISITION_COMPLETED",
        }
        return M336IAcquisitionLedgerReceipt(**body, receipt_hash=content_hash(body))


def build_m336i_final_acquisition_authorization(
    **values,
) -> M336IFinalAcquisitionAuthorization:
    body = {
        "schema_version": 1,
        "authorization_role": M336I_FROZEN_AUTHORIZATION_ROLE,
        **values,
    }
    authorization = M336IFinalAcquisitionAuthorization(
        **body, authorization_hash=content_hash(body)
    )
    verify_m336i_final_acquisition_authorization(authorization)
    return authorization


def final_acquisition_authorization_from_dict(
    value: dict,
) -> M336IFinalAcquisitionAuthorization:
    if not isinstance(value, dict) or set(value) != set(
        M336IFinalAcquisitionAuthorization.__dataclass_fields__
    ):
        raise ValueError("M336I final acquisition authorization fields changed")
    converted = {
        **value,
        "allowed_network_hosts": tuple(value["allowed_network_hosts"]),
    }
    authorization = M336IFinalAcquisitionAuthorization(**converted)
    verify_m336i_final_acquisition_authorization(authorization)
    return authorization


def verify_m336i_final_acquisition_authorization(
    authorization: M336IFinalAcquisitionAuthorization,
) -> None:
    if not isinstance(authorization, M336IFinalAcquisitionAuthorization):
        raise TypeError("M336I final acquisition authorization must be typed")
    body = asdict(authorization)
    claimed = body.pop("authorization_hash")
    hash_names = tuple(
        item.name
        for item in fields(authorization)
        if item.name.endswith("_hash") or item.name.endswith("_identity")
    )
    if (
        authorization.schema_version != 1
        or authorization.authorization_role != M336I_FROZEN_AUTHORIZATION_ROLE
        or authorization.acquisition_mode not in {"FINAL", "REHEARSAL"}
        or _GIT_SHA.fullmatch(authorization.exact_q23_sha) is None
        or _GIT_SHA.fullmatch(authorization.f24_parent_sha) is None
        or any(
            _SHA256.fullmatch(getattr(authorization, name)) is None
            for name in hash_names
        )
        or authorization.acquisition_run_id == ""
        or authorization.allowed_network_hosts
        != tuple(sorted(set(authorization.allowed_network_hosts)))
        or authorization.expected_global_acquisition_count != 1
        or authorization.expected_windows_acquisition_count != 1
        or authorization.expected_karina_acquisition_count != 0
        or not authorization.branch_ref.startswith("refs/heads/")
        or content_hash(body) != claimed
    ):
        raise ValueError("M336I final acquisition authorization is invalid")


def acquisition_provider_identity() -> tuple[str, str]:
    return (
        bytes_hash(Path(__file__).resolve(strict=True).read_bytes()),
        content_hash(str(inspect.signature(run_m336i_frozen_final_acquisition))),
    )


def compute_m336i_freeze_tree_identity(repository: Path) -> str:
    root = repository.resolve(strict=True)
    raw = _git(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        binary=True,
    )
    freeze_root = root / Path(M336I_FROZEN_AUTHORIZATION_PATH).parent
    explicit_freeze_paths = {
        path.relative_to(root).as_posix()
        for path in freeze_root.rglob("*")
        if path.is_file()
    }
    paths = tuple(
        sorted(
            {
                item.decode("utf-8", errors="strict")
                for item in raw.split(b"\0")
                if item
                and item.decode("utf-8", errors="strict")
                not in M336I_FREEZE_IDENTITY_EXCLUSIONS
            }
            | (explicit_freeze_paths - M336I_FREEZE_IDENTITY_EXCLUSIONS),
            key=lambda item: item.encode("utf-8"),
        )
    )
    return content_hash(
        tuple((path, bytes_hash((root / path).read_bytes())) for path in paths)
    )


def compute_m336i_commit_tree_identity(repository: Path, commit: str) -> str:
    root = repository.resolve(strict=True)
    raw = _git(root, "ls-tree", "-r", "-z", commit, binary=True)
    if not raw:
        raise ValueError("M336I implementation tree is empty")
    return bytes_hash(raw)


def validate_m336i_candidate_pool(pool: dict) -> tuple[dict, ...]:
    if not isinstance(pool, dict):
        raise TypeError("M336I candidate pool must be an object")
    body = dict(pool)
    claimed = body.pop("pool_hash", None)
    candidates = tuple(pool.get("candidates", ()))
    family_ids = tuple(item.get("family_id") for item in candidates)
    organizations = Counter(item.get("organization_id") for item in candidates)
    risks = Counter(item.get("metadata_compilation_risk") for item in candidates)
    if (
        content_hash(body) != claimed
        or pool.get("schema_version") != 3
        or pool.get("policy_version") != "m336g.metadata-pool.v1"
        or pool.get("candidate_count") != len(candidates)
        or pool.get("required_candidate_count") != 0
        or pool.get("optional_candidate_count") != len(candidates)
        or pool.get("pre_f22_source_body_bytes_received") != 0
        or pool.get("claims_final_eligibility") is not False
        or pool.get("organization_count") != len(organizations)
        or pool.get("maximum_candidates_per_organization")
        != max(organizations.values(), default=0)
        or pool.get("metadata_compilation_risk_counts")
        != [list(item) for item in sorted(risks.items())]
        or len(family_ids) != len(set(family_ids))
        or family_ids != tuple(sorted(family_ids, key=lambda item: item.encode()))
        or any(item.get("requirement") != "OPTIONAL" for item in candidates)
    ):
        raise ValueError("M336I frozen candidate pool is invalid")
    required = {
        "family_id",
        "organization_id",
        "coordinate",
        "source_url",
        "scm_repository",
        "scm_commit",
        "source_content_length",
        "metadata_compilation_risk",
        "requirement",
        "policy_hash",
    }
    for item in candidates:
        candidate_body = dict(item)
        policy_hash = candidate_body.pop("policy_hash", None)
        if (
            not required.issubset(item)
            or content_hash(candidate_body) != policy_hash
            or item["source_content_length"] <= 0
            or not item["scm_commit"]
            or urllib.parse.urlsplit(item["source_url"]).scheme != "https"
            or urllib.parse.urlsplit(item["source_url"]).hostname is None
            or urllib.parse.urlsplit(item["scm_repository"]).hostname is None
        ):
            raise ValueError("M336I frozen candidate policy is invalid")
    return candidates


def validate_m336i_acquisition_policy(value: dict) -> dict:
    if not isinstance(value, dict):
        raise TypeError("M336I acquisition policy must be an object")
    body = dict(value)
    claimed = body.pop("acquisition_policy_hash", None)
    if (
        content_hash(body) != claimed
        or value.get("acquisition_run_id") != M336I_FINAL_ACQUISITION_RUN_ID
        or value.get("acquire_every_frozen_candidate") is not True
        or value.get("replacement_candidates_allowed") is not False
        or value.get("adaptive_family_substitution_allowed") is not False
        or value.get("global_acquisition_count") != 1
        or value.get("windows_acquisition_count") != 1
        or value.get("karina_acquisition_count") != 0
        or value.get("acquisition_reruns_allowed") is not False
    ):
        raise ValueError("M336I acquisition policy is invalid")
    return value


def run_m336i_frozen_final_acquisition(
    request: M336IFinalAcquisitionRequest,
    *,
    maven_provider=None,
    scm_provider=None,
    acquire_one=None,
    crash_after: str | None = None,
    event_callback=None,
) -> M336IFinalAcquisitionReceipt:
    """Validate the frozen authority, spend once, and acquire the entire pool."""

    context, pool, policy, worktrees = _validate_request_before_side_effects(request)
    ledger = M336IFinalAcquisitionLedger(
        request.acquisition_ledger, git_worktrees=worktrees
    )
    if ledger.events():
        raise ValueError("M336I acquisition capacity is already spent or blocked")
    ledger.append(
        "AUTHORIZATION_VALIDATED",
        context_hash=context,
        operation_hash=request.authorization.authorization_hash,
    )
    _notify(event_callback, "AUTHORIZATION_VALIDATED", ledger.events()[-1].event_hash)
    _maybe_crash(crash_after, "AUTHORIZATION_VALIDATED")
    ledger.append(
        "ACQUISITION_RESERVED",
        context_hash=context,
        operation_hash=content_hash(policy),
    )
    _notify(event_callback, "ACQUISITION_RESERVED", ledger.events()[-1].event_hash)
    _maybe_crash(crash_after, "ACQUISITION_RESERVED")
    ledger.append(
        "ACQUISITION_STARTED", context_hash=context, operation_hash=pool["pool_hash"]
    )
    _maybe_crash(crash_after, "ACQUISITION_STARTED")
    try:
        kwargs = {}
        if maven_provider is not None:
            kwargs["maven_provider"] = maven_provider
        if scm_provider is not None:
            kwargs["scm_provider"] = scm_provider
        if acquire_one is not None:
            kwargs["acquire_one"] = acquire_one
        unused_protocol = RunProtocolLedger(
            request.private_acquisition_output.parent / "unused-m336e-protocol.jsonl",
            git_worktrees=worktrees,
        )
        preflight = run_fresh_acquisition_and_preflight(
            pool=pool,
            vault_root=request.vault_destination,
            authority_statement=request.authority_statement,
            f20_sha=request.supplied_f24_sha,
            timestamp="1970-01-01T00:00:00Z",
            host=request.platform_role,
            ledger=unused_protocol,
            selected_source_output=request.unused_selected_source_output,
            git_worktrees=worktrees,
            validate_pool=validate_m336i_candidate_pool,
            record_protocol=False,
            perform_selector=False,
            acquisition_run_id=request.authorization.acquisition_run_id,
            **kwargs,
        )
        _write_private_preflight(request.private_acquisition_output, preflight)
        if preflight.status != "PASS":
            raise ValueError("M336I acquisition qualification preflight is blocked")
        receipt = _build_public_receipt(request, preflight, pool, policy, ledger)
        write_canonical_json(request.public_receipt_output, receipt)
        ledger.append(
            "ACQUISITION_COMPLETED",
            context_hash=context,
            operation_hash=receipt.receipt_hash,
        )
        _notify(
            event_callback,
            "ACQUISITION_COMPLETED",
            ledger.events()[-1].event_hash,
        )
        _maybe_crash(crash_after, "ACQUISITION_COMPLETED")
        return receipt
    except BaseException as error:
        if not isinstance(error, M336IAcquisitionCrash):
            try:
                ledger.append(
                    "ACQUISITION_FAILED",
                    context_hash=context,
                    operation_hash=content_hash(type(error).__name__),
                )
            except ValueError:
                pass
            if not request.public_receipt_output.exists():
                failure_body = {
                    "schema_version": 1,
                    "contract_role": "PUBLIC_SAFE_ACQUISITION_FAILURE_RECEIPT",
                    "acquisition_mode": request.authorization.acquisition_mode,
                    "exact_f24_sha": request.supplied_f24_sha,
                    "authorization_hash": request.authorization.authorization_hash,
                    "candidate_pool_hash": pool["pool_hash"],
                    "acquisition_policy_hash": policy["acquisition_policy_hash"],
                    "failure_class": type(error).__name__,
                    "failure_message_hash": content_hash(str(error)),
                    "acquisition_ledger_receipt_hash": ledger.receipt().receipt_hash,
                    "status": "BLOCKED",
                }
                write_canonical_json(
                    request.public_receipt_output,
                    {
                        **failure_body,
                        "receipt_hash": content_hash(failure_body),
                    },
                )
        raise


def _validate_request_before_side_effects(request):
    if not isinstance(request, M336IFinalAcquisitionRequest):
        raise TypeError("M336I acquisition request must be typed")
    authorization = request.authorization
    verify_m336i_final_acquisition_authorization(authorization)
    if request.platform_role != "WINDOWS":
        raise ValueError("M336I source acquisition is Windows-only")
    repository = request.repository.resolve(strict=True)
    worktrees = _git_worktrees(repository)
    paths = (
        request.candidate_pool,
        request.acquisition_policy,
        request.denylist,
        request.authority_root,
        request.authority_statement,
        request.frozen_route_registry,
        request.frozen_route_manifest,
        request.selector_policy,
        request.threshold_manifest,
        request.publication_boundary_contract,
        request.public_artifact_contract,
        request.compiler_jdk_identities,
        request.karina_host_identity_receipt,
    )
    if any(not Path(item).is_file() for item in paths):
        raise ValueError("M336I frozen acquisition input is missing")
    external = (
        request.acquisition_ledger,
        request.vault_destination,
        request.private_acquisition_output,
        request.public_receipt_output,
        request.unused_selected_source_output,
    )
    public = request.public_staging_root.resolve(strict=False)
    for path in external:
        resolved = Path(path).resolve(strict=False)
        if any(_is_relative_to(resolved, root) for root in worktrees) or _paths_overlap(
            resolved, public
        ):
            raise ValueError(
                "M336I private acquisition path overlaps Git/public staging"
            )
    if any(Path(path).exists() for path in external):
        raise FileExistsError("M336I final acquisition destinations must be fresh")
    head = _git(repository, "rev-parse", "HEAD^{commit}").strip()
    status = _git(repository, "status", "--porcelain=v1")
    parent = _git(repository, "rev-parse", "HEAD^1").strip()
    r24 = _git(repository, "rev-parse", "HEAD~2").strip()
    q23 = _git(repository, "rev-parse", "HEAD~3").strip()
    merge_count = int(
        _git(
            repository,
            "rev-list",
            "--count",
            "--merges",
            f"{authorization.exact_q23_sha}..HEAD",
        ).strip()
    )
    upstream = _git(repository, "rev-parse", "@{upstream}^{commit}").strip()
    remote = _remote_branch_sha(repository, authorization.branch_ref)
    if (
        head != request.supplied_f24_sha
        or status
        or parent != authorization.f24_parent_sha
        or q23 != authorization.exact_q23_sha
        or compute_m336i_commit_tree_identity(repository, r24)
        != authorization.r24_implementation_tree_identity
        or merge_count != 0
        or upstream != head
        or remote != head
        or compute_m336i_freeze_tree_identity(repository)
        != authorization.f24_freeze_tree_identity
    ):
        raise ValueError("M336I exact-F24 Git precondition failed")
    frozen_authorization = strict_json_file(
        repository / M336I_FROZEN_AUTHORIZATION_PATH
    )
    freeze_manifest = strict_json_file(repository / M336I_FREEZE_MANIFEST_PATH)
    freeze_body = dict(freeze_manifest)
    freeze_hash = freeze_body.pop("manifest_hash", None)
    if (
        frozen_authorization != json.loads(canonical_json(authorization))
        or content_hash(freeze_body) != freeze_hash
        or freeze_manifest.get("authorization_hash") != authorization.authorization_hash
        or freeze_manifest.get("f24_freeze_tree_identity")
        != authorization.f24_freeze_tree_identity
        or freeze_manifest.get("f24_parent_sha") != authorization.f24_parent_sha
        or freeze_manifest.get("q24_evidence_identity")
        != authorization.q24_evidence_identity
        or freeze_manifest.get("r24_implementation_tree_identity")
        != authorization.r24_implementation_tree_identity
    ):
        raise ValueError("M336I frozen authorization object is not exact")
    pool = strict_json_file(request.candidate_pool)
    policy = strict_json_file(request.acquisition_policy)
    validate_m336i_candidate_pool(pool)
    validate_m336i_acquisition_policy(policy)
    from ai_brain.stage3.acquisition.m336i_registry import (
        build_m336i_final_java_route_manifest,
        build_m336i_final_java_route_registry,
    )

    live_registry = build_m336i_final_java_route_registry()
    live_manifest = build_m336i_final_java_route_manifest(live_registry)
    frozen_registry = strict_json_file(request.frozen_route_registry)
    frozen_manifest = strict_json_file(request.frozen_route_manifest)
    selector_policy = strict_json_file(request.selector_policy)
    threshold_manifest = strict_json_file(request.threshold_manifest)
    publication_boundary = strict_json_file(request.publication_boundary_contract)
    public_contract = strict_json_file(request.public_artifact_contract)
    jdk_identities = strict_json_file(request.compiler_jdk_identities)
    karina_host = strict_json_file(request.karina_host_identity_receipt)
    for value, hash_field in (
        (policy, "acquisition_policy_hash"),
        (strict_json_file(request.denylist), "denylist_hash"),
        (strict_json_file(request.authority_root), "authority_root_hash"),
        (selector_policy, "selector_policy_hash"),
        (threshold_manifest, "threshold_manifest_hash"),
        (publication_boundary, "publication_boundary_policy_hash"),
        (public_contract, "public_artifact_contract_hash"),
        (jdk_identities, "compiler_jdk_identities_hash"),
        (karina_host, "receipt_hash"),
    ):
        _verify_object_hash(value, hash_field)
    source_hash, signature_hash = acquisition_provider_identity()
    artifact_checks = {
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": policy["acquisition_policy_hash"],
        "denylist_hash": strict_json_file(request.denylist)["denylist_hash"],
        "authority_root_hash": strict_json_file(request.authority_root)[
            "authority_root_hash"
        ],
        "selector_policy_hash": selector_policy["selector_policy_hash"],
        "threshold_manifest_hash": threshold_manifest["threshold_manifest_hash"],
        "publication_boundary_hash": publication_boundary[
            "publication_boundary_policy_hash"
        ],
        "public_artifact_contract_hash": public_contract[
            "public_artifact_contract_hash"
        ],
        "windows_public_jdk_identity_receipt_hash": jdk_identities[
            "windows_public_jdk_receipt_hash"
        ],
        "karina_public_jdk_identity_receipt_hash": jdk_identities[
            "karina_public_jdk_receipt_hash"
        ],
        "karina_stable_host_identity_receipt_hash": karina_host["receipt_hash"],
        "route_registry_hash": live_registry.registry_hash,
        "route_manifest_hash": live_manifest.manifest_hash,
        "acquisition_provider_source_hash": source_hash,
        "acquisition_provider_callable_signature_hash": signature_hash,
    }
    if any(
        getattr(authorization, name) != value for name, value in artifact_checks.items()
    ):
        raise ValueError("M336I live/frozen authorization binding changed")
    if frozen_registry != json.loads(
        canonical_json(live_registry)
    ) or frozen_manifest != json.loads(canonical_json(live_manifest)):
        raise ValueError("M336I live route differs from frozen registry/manifest")
    hosts = _pool_hosts(pool)
    if (
        hosts - set(authorization.allowed_network_hosts)
        or tuple(policy["allowed_network_hosts"]) != authorization.allowed_network_hosts
    ):
        raise ValueError("M336I frozen network allowlist does not cover the pool")
    context = content_hash(
        (
            authorization.authorization_hash,
            request.supplied_f24_sha,
            pool["pool_hash"],
            policy["acquisition_policy_hash"],
        )
    )
    return context, pool, policy, worktrees


def _verify_object_hash(value: dict, hash_field: str) -> None:
    if not isinstance(value, dict):
        raise TypeError("M336I frozen authority artifact must be an object")
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I frozen {hash_field} does not match content")


def _build_public_receipt(request, preflight, pool, policy, ledger):
    acquisition = preflight.acquisition_report
    acquired = sum(
        item["source_jar_sha256"] != "0" * 64 for item in acquisition["receipts"]
    )
    java_files = sum(
        row.canonical_path.endswith(".java")
        for row in preflight.portable_vault_manifest.rows
    )
    qualification = preflight.qualification_report
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_ACQUISITION_RECEIPT",
        "acquisition_mode": request.authorization.acquisition_mode,
        "exact_f24_sha": request.supplied_f24_sha,
        "authorization_hash": request.authorization.authorization_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": policy["acquisition_policy_hash"],
        "acquired_candidate_count": acquired,
        "failed_candidate_count": len(acquisition["receipts"]) - acquired,
        "vault_file_count": preflight.portable_vault_manifest.file_count,
        "java_file_count": java_files,
        "portable_vault_tree_hash": preflight.portable_vault_manifest.portable_tree_hash,
        "portable_vault_manifest_hash": preflight.portable_vault_manifest.manifest_hash,
        "legal_document_count": qualification["legal_document_count"],
        "unknown_legal_document_role_count": qualification[
            "unknown_legal_document_role_count"
        ],
        "network_host_counts": _network_host_counts(pool),
        "global_acquisition_reservation_count": 1,
        "global_acquisition_invocation_count": 1,
        "windows_acquisition_invocation_count": 1,
        "karina_acquisition_invocation_count": 0,
        "acquisition_rerun_count": ledger.receipt().acquisition_rerun_count,
        "replacement_candidate_count": 0,
        "qualification_report_hash": qualification["report_hash"],
        "source_entry_binding_manifest_hash": preflight.source_entry_binding_manifest.manifest_hash,
        "selectability_census_hash": preflight.selectability_census.census_hash,
        "status": "PASS",
    }
    return M336IFinalAcquisitionReceipt(**body, receipt_hash=content_hash(body))


def _write_private_preflight(root: Path, preflight: FreshAcquisitionPreflight) -> None:
    root.mkdir(parents=True, exist_ok=False)
    values = {
        "acquisition_receipts.json": preflight.acquisition_report,
        "candidate_qualification.json": preflight.qualification_report,
        "portable_vault_manifest.json": preflight.portable_vault_manifest,
        "source_entry_binding_manifest.json": preflight.source_entry_binding_manifest,
        "selectability_census.json": preflight.selectability_census,
        "legacy_selector_feasibility.json": preflight.feasibility_proof,
        "source_overlap_report.json": preflight.source_overlap_report,
        "disclosure_append.json": preflight.disclosure_append,
    }
    for name, value in values.items():
        write_canonical_json(root / name, value)


def _verify_acquisition_event_order(events) -> None:
    names = tuple(item.event for item in events)
    if names and names[-1] == "ACQUISITION_FAILED":
        prefix = names[:-1]
        if prefix not in (M336I_ACQUISITION_EVENTS[:2], M336I_ACQUISITION_EVENTS[:3]):
            raise ValueError("M336I failed acquisition event chain is invalid")
    elif names != M336I_ACQUISITION_EVENTS[: len(names)]:
        raise ValueError("M336I acquisition event chain is invalid")


def _strict_json_bytes(raw: bytes):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("M336I ledger JSON has a duplicate key")
            value[key] = item
        return value

    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)


def _maybe_crash(requested: str | None, boundary: str) -> None:
    if requested == boundary:
        raise M336IAcquisitionCrash(f"injected crash after {boundary}")


def _notify(callback, event: str, event_hash: str) -> None:
    if callback is not None:
        callback(event, event_hash)


def _git(root: Path, *args: str, binary: bool = False):
    result = subprocess.run(("git", *args), cwd=root, check=True, capture_output=True)
    return (
        result.stdout
        if binary
        else result.stdout.decode("utf-8", errors="strict").strip()
    )


def _git_worktrees(repository: Path) -> tuple[Path, ...]:
    value = _git(repository, "worktree", "list", "--porcelain")
    return tuple(
        Path(line.removeprefix("worktree ")).resolve(strict=True)
        for line in value.splitlines()
        if line.startswith("worktree ")
    )


def _remote_branch_sha(repository: Path, branch_ref: str) -> str:
    output = _git(repository, "ls-remote", "--exit-code", "origin", branch_ref)
    fields = output.split()
    if len(fields) != 2 or fields[1] != branch_ref:
        raise ValueError("M336I remote branch identity is ambiguous")
    return fields[0]


def _pool_hosts(pool: dict) -> set[str]:
    return {
        host
        for item in pool["candidates"]
        for key in ("source_url", "pom_url", "scm_archive_head_url")
        if (host := urllib.parse.urlsplit(item[key]).hostname)
    }


def _network_host_counts(pool: dict) -> tuple[tuple[str, int], ...]:
    counts = {}
    for item in pool["candidates"]:
        for key in ("source_url", "pom_url", "scm_archive_head_url"):
            host = urllib.parse.urlsplit(item[key]).hostname
            if host:
                counts[host] = counts.get(host, 0) + 1
    return tuple(sorted(counts.items()))


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or _is_relative_to(left, right) or _is_relative_to(right, left)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
