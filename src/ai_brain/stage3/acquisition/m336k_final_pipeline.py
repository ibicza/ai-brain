"""Frozen candidate-isolated final acquisition route for M-33.6k."""

from __future__ import annotations

import subprocess
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    FreshAcquisitionPreflight,
    run_fresh_acquisition_and_preflight,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336i_acquisition import (
    validate_m336i_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k_acquisition import (
    CandidateAcquisitionOutcome,
    M336KAcquisitionLedger,
    M336KAcquisitionLedgerReceipt,
    M336KGlobalAcquisitionReceipt,
    build_global_acquisition_receipt,
)
from ai_brain.stage3.acquisition.m336k_archive import ArchiveInspectionPolicyV2

M336K_FINAL_AUTHORIZATION_ROLE = "M336K_FINAL_ACQUISITION_AUTHORIZATION_V1"
M336K_FINAL_RUN_ID = "m336k.final-java.global-acquisition.v1"


@dataclass(frozen=True)
class M336KFinalAcquisitionAuthorization:
    schema_version: int
    authorization_role: str
    exact_r27_sha: str
    exact_q27_sha: str
    branch_ref: str
    acquisition_run_id: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    archive_policy_hash: str
    candidate_terminal_policy_hash: str
    global_continuation_policy_hash: str
    route_manifest_hash: str
    registry_manifest_hash: str
    threshold_manifest_hash: str
    allowed_network_hosts: tuple[str, ...]
    expected_global_acquisition_count: int
    expected_windows_acquisition_count: int
    expected_karina_acquisition_count: int
    candidate_retries_allowed: bool
    candidate_replacements_allowed: bool
    pre_f27_source_body_bytes: int
    authorization_hash: str


@dataclass(frozen=True)
class M336KFinalAcquisitionResult:
    preflight: FreshAcquisitionPreflight
    candidate_outcomes: tuple[CandidateAcquisitionOutcome, ...]
    global_receipt: M336KGlobalAcquisitionReceipt
    ledger_receipt: M336KAcquisitionLedgerReceipt
    public_receipt: dict


def m336k_candidate_terminal_policy() -> dict:
    body = {
        "schema_version": 1,
        "policy_version": "m336k.candidate-terminal.v1",
        "one_terminal_receipt_per_candidate": True,
        "candidate_local_failures_continue": True,
        "unexpected_exceptions_are_global": True,
        "rejected_archives_may_enter_source_index": False,
        "rejected_archives_may_enter_census": False,
        "candidate_retry_count": 0,
        "candidate_replacement_count": 0,
    }
    return {**body, "policy_hash": content_hash(body)}


def m336k_global_continuation_policy() -> dict:
    body = {
        "schema_version": 1,
        "policy_version": "m336k.global-continuation.v1",
        "all_candidates_optional": True,
        "candidate_rejection_is_global_failure": False,
        "all_candidates_terminal_before_completion": True,
        "pool_gate_after_global_completion": True,
        "global_failure_on_missing_terminal": True,
        "global_failure_on_unknown_exception": True,
        "global_failure_on_vault_or_policy_mismatch": True,
    }
    return {**body, "policy_hash": content_hash(body)}


def build_m336k_final_acquisition_authorization(
    **values,
) -> M336KFinalAcquisitionAuthorization:
    body = {
        "schema_version": 1,
        "authorization_role": M336K_FINAL_AUTHORIZATION_ROLE,
        **values,
    }
    authorization = M336KFinalAcquisitionAuthorization(
        **body, authorization_hash=content_hash(body)
    )
    verify_m336k_final_acquisition_authorization(authorization)
    return authorization


def m336k_final_acquisition_authorization_from_dict(
    value: dict,
) -> M336KFinalAcquisitionAuthorization:
    if not isinstance(value, dict) or set(value) != set(
        M336KFinalAcquisitionAuthorization.__dataclass_fields__
    ):
        raise ValueError("M336K final authorization fields changed")
    authorization = M336KFinalAcquisitionAuthorization(
        **{**value, "allowed_network_hosts": tuple(value["allowed_network_hosts"])}
    )
    verify_m336k_final_acquisition_authorization(authorization)
    return authorization


def verify_m336k_final_acquisition_authorization(
    authorization: M336KFinalAcquisitionAuthorization,
) -> None:
    body = asdict(authorization)
    claimed = body.pop("authorization_hash")
    hashes = (
        authorization.exact_r27_sha,
        authorization.exact_q27_sha,
        authorization.candidate_pool_hash,
        authorization.acquisition_policy_hash,
        authorization.archive_policy_hash,
        authorization.candidate_terminal_policy_hash,
        authorization.global_continuation_policy_hash,
        authorization.route_manifest_hash,
        authorization.registry_manifest_hash,
        authorization.threshold_manifest_hash,
    )
    if (
        authorization.schema_version != 1
        or authorization.authorization_role != M336K_FINAL_AUTHORIZATION_ROLE
        or authorization.acquisition_run_id != M336K_FINAL_RUN_ID
        or not authorization.branch_ref.startswith("refs/heads/")
        or any(
            not _hash(value, 40 if index < 2 else 64)
            for index, value in enumerate(hashes)
        )
        or tuple(sorted(set(authorization.allowed_network_hosts)))
        != authorization.allowed_network_hosts
        or not authorization.allowed_network_hosts
        or any(not _host(value) for value in authorization.allowed_network_hosts)
        or authorization.expected_global_acquisition_count != 1
        or authorization.expected_windows_acquisition_count != 1
        or authorization.expected_karina_acquisition_count != 0
        or authorization.candidate_retries_allowed is not False
        or authorization.candidate_replacements_allowed is not False
        or authorization.pre_f27_source_body_bytes != 0
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid M336K final acquisition authorization")


def run_m336k_frozen_final_acquisition(
    *,
    repository: Path,
    expected_f27_sha: str,
    pool: dict,
    authorization: M336KFinalAcquisitionAuthorization,
    acquisition_policy: dict,
    authority_statement: Path,
    vault_root: Path,
    ledger: M336KAcquisitionLedger,
    private_preflight_path: Path,
    unused_selected_source_output: Path,
    host: str,
    maven_provider=None,
    scm_provider=None,
) -> M336KFinalAcquisitionResult:
    """Spend one final acquisition while isolating every expected candidate fault."""

    repository = repository.resolve(strict=True)
    _require_clean_exact_lineage(
        repository,
        expected_head=expected_f27_sha,
        expected_parent=authorization.exact_q27_sha,
        branch_ref=authorization.branch_ref,
    )
    candidates = validate_m336i_candidate_pool(pool)
    verify_m336k_final_acquisition_authorization(authorization)
    _verify_final_inputs(pool, candidates, authorization, acquisition_policy)
    if private_preflight_path.exists():
        raise FileExistsError("M336K private final preflight must be fresh")
    if private_preflight_path.is_relative_to(repository):
        raise ValueError("M336K private final preflight must remain outside Git")
    outcomes: list[CandidateAcquisitionOutcome] = []
    context_hash = content_hash(
        (
            expected_f27_sha,
            authorization.authorization_hash,
            authorization.candidate_pool_hash,
        )
    )
    ledger.append(
        "AUTHORIZATION_VALIDATED",
        context_hash=context_hash,
        operation_hash=authorization.authorization_hash,
    )
    ledger.append(
        "ACQUISITION_RESERVED",
        context_hash=context_hash,
        operation_hash=authorization.acquisition_policy_hash,
    )
    ledger.append(
        "ACQUISITION_STARTED",
        context_hash=context_hash,
        operation_hash=authorization.candidate_pool_hash,
    )

    def terminal(outcome: CandidateAcquisitionOutcome) -> None:
        outcomes.append(outcome)

    def all_terminal() -> None:
        families = tuple(item.terminal_receipt.candidate_family_id for item in outcomes)
        expected = tuple(item["family_id"] for item in candidates)
        if families != expected or len(set(families)) != len(families):
            raise RuntimeError("M336K final terminal accounting mismatch")
        ledger.append(
            "ALL_CANDIDATES_TERMINAL",
            context_hash=context_hash,
            operation_hash=content_hash(
                tuple(item.terminal_receipt.receipt_hash for item in outcomes)
            ),
        )

    try:
        unused_legacy = RunProtocolLedger(
            private_preflight_path.with_name("unused-m336e-ledger.jsonl"),
            git_worktrees=(repository,),
        )
        preflight = run_fresh_acquisition_and_preflight(
            pool=pool,
            vault_root=vault_root,
            authority_statement=authority_statement,
            f20_sha=expected_f27_sha,
            timestamp="1970-01-01T00:00:00Z",
            host=host,
            ledger=unused_legacy,
            selected_source_output=unused_selected_source_output,
            git_worktrees=(repository,),
            maven_provider=maven_provider,
            scm_provider=scm_provider,
            validate_pool=validate_m336i_candidate_pool,
            record_protocol=False,
            perform_selector=False,
            acquisition_run_id=authorization.acquisition_run_id,
            candidate_outcome_callback=terminal,
            all_candidates_terminal_callback=all_terminal,
        )
        private_preflight_path.parent.mkdir(parents=True, exist_ok=True)
        private_preflight_path.write_text(
            canonical_json(asdict(preflight)) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        global_receipt = build_global_acquisition_receipt(
            acquisition_run_id=authorization.acquisition_run_id,
            candidate_count=len(candidates),
            attempted_count=len(outcomes),
            outcomes=tuple(outcomes),
            vault_manifest_hash=preflight.portable_vault_manifest.portable_tree_hash,
        )
        ledger.append(
            "ACQUISITION_COMPLETED",
            context_hash=context_hash,
            operation_hash=global_receipt.receipt_hash,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        ledger.append(
            "ACQUISITION_FAILED",
            context_hash=context_hash,
            operation_hash=content_hash(type(error).__name__),
        )
        raise
    public_receipt = _public_final_receipt(
        expected_f27_sha,
        authorization,
        tuple(outcomes),
        preflight,
        global_receipt,
        ledger.receipt(),
    )
    return M336KFinalAcquisitionResult(
        preflight,
        tuple(outcomes),
        global_receipt,
        ledger.receipt(),
        public_receipt,
    )


def _verify_final_inputs(pool, candidates, authorization, acquisition_policy) -> None:
    policy_body = dict(acquisition_policy)
    policy_hash = policy_body.pop("acquisition_policy_hash", None)
    organizations = Counter(item["organization_id"] for item in candidates)
    pool_hosts = tuple(
        sorted(
            {
                host
                for item in candidates
                for key in (
                    "source_url",
                    "pom_url",
                    "scm_repository",
                    "scm_archive_head_url",
                )
                if (host := _url_host(item.get(key))) is not None
            }
        )
    )
    terminal_policy = m336k_candidate_terminal_policy()
    continuation_policy = m336k_global_continuation_policy()
    archive_policy = ArchiveInspectionPolicyV2.frozen_default()
    if (
        content_hash(policy_body) != policy_hash
        or policy_hash != authorization.acquisition_policy_hash
        or acquisition_policy.get("schema_version") != 1
        or acquisition_policy.get("policy_version") != "m336k.final-acquisition.v3"
        or acquisition_policy.get("acquisition_run_id")
        != authorization.acquisition_run_id
        or acquisition_policy.get("candidate_pool_hash") != pool["pool_hash"]
        or acquisition_policy.get("archive_policy_hash") != archive_policy.policy_hash
        or acquisition_policy.get("candidate_terminal_policy_hash")
        != terminal_policy["policy_hash"]
        or acquisition_policy.get("global_continuation_policy_hash")
        != continuation_policy["policy_hash"]
        or acquisition_policy.get("allowed_network_hosts") != list(pool_hosts)
        or acquisition_policy.get("global_acquisition_count") != 1
        or acquisition_policy.get("windows_acquisition_count") != 1
        or acquisition_policy.get("karina_acquisition_count") != 0
        or acquisition_policy.get("candidate_retries_allowed") is not False
        or acquisition_policy.get("candidate_replacements_allowed") is not False
        or acquisition_policy.get("acquire_every_frozen_candidate") is not True
        or acquisition_policy.get("pre_f27_source_body_bytes") != 0
        or authorization.candidate_pool_hash != pool["pool_hash"]
        or authorization.archive_policy_hash != archive_policy.policy_hash
        or authorization.candidate_terminal_policy_hash
        != terminal_policy["policy_hash"]
        or authorization.global_continuation_policy_hash
        != continuation_policy["policy_hash"]
        or authorization.allowed_network_hosts != pool_hosts
        or len(candidates) < 64
        or len(organizations) < 56
        or max(organizations.values(), default=0) > 2
        or any(item["requirement"] != "OPTIONAL" for item in candidates)
    ):
        raise ValueError("M336K frozen final inputs are inconsistent")


def _public_final_receipt(
    f27_sha,
    authorization,
    outcomes,
    preflight,
    global_receipt,
    ledger_receipt,
) -> dict:
    statuses = Counter(item.terminal_receipt.terminal_status.value for item in outcomes)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_FINAL_ACQUISITION_RECEIPT",
        "exact_f27_sha": f27_sha,
        "authorization_hash": authorization.authorization_hash,
        "acquisition_run_id": authorization.acquisition_run_id,
        "candidate_pool_hash": authorization.candidate_pool_hash,
        "acquisition_policy_hash": authorization.acquisition_policy_hash,
        "archive_policy_hash": authorization.archive_policy_hash,
        "candidate_count": global_receipt.candidate_count,
        "attempted_count": global_receipt.attempted_count,
        "terminal_count": global_receipt.terminal_count,
        "terminal_status_counts": tuple(sorted(statuses.items())),
        "missing_terminal_count": global_receipt.missing_terminal_count,
        "duplicate_terminal_count": global_receipt.duplicate_terminal_count,
        "unexpected_global_failure_count": (
            global_receipt.unexpected_global_failure_count
        ),
        "candidate_retry_count": global_receipt.candidate_retry_count,
        "candidate_replacement_count": global_receipt.candidate_replacement_count,
        "authoritative_archive_inspection_count": (
            global_receipt.authoritative_archive_inspection_count
        ),
        "vault_manifest_hash": global_receipt.vault_manifest_hash,
        "candidate_terminal_manifest_hash": (
            global_receipt.candidate_terminal_manifest_hash
        ),
        "global_acquisition_status": global_receipt.status,
        "pool_qualification_status": preflight.status,
        "selectable_file_count": preflight.selectability_census.selectable_file_count,
        "selectable_root_count": preflight.selectability_census.selectable_root_count,
        "balanced_capacity": preflight.feasibility_proof.balanced_capacity,
        "closure_feasibility": (
            "PASS"
            if preflight.feasibility_proof.hard_requirements_satisfied
            else "BLOCKED"
        ),
        "ledger_receipt_hash": ledger_receipt.receipt_hash,
        "status": "ACQUISITION_COMPLETED",
    }
    return {**body, "receipt_hash": content_hash(body)}


def _require_clean_exact_lineage(
    repository: Path, *, expected_head: str, expected_parent: str, branch_ref: str
) -> None:
    head = _git(repository, "rev-parse", "HEAD^{commit}")
    parent = _git(repository, "rev-parse", "HEAD^1")
    branch = _git(repository, "symbolic-ref", "HEAD")
    status = _git(repository, "status", "--porcelain=v1")
    if (
        head != expected_head
        or parent != expected_parent
        or branch != branch_ref
        or status
        or _git(
            repository, "rev-list", "--merges", "--count", f"{expected_parent}..{head}"
        )
        != "0"
    ):
        raise ValueError("M336K final acquisition requires a clean linear exact F27")


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _url_host(value) -> str | None:
    if not isinstance(value, str):
        return None
    return urllib.parse.urlsplit(value).hostname


def _host(value: str) -> bool:
    return value == value.lower() and "/" not in value and ":" not in value


def _hash(value: str, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and set(value) <= set("0123456789abcdef")
    )
