"""Count-neutral, candidate-isolated one-shot acquisition for M-33.6k.2."""

from __future__ import annotations

import subprocess
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    FreshAcquisitionPreflight,
    run_fresh_acquisition_and_preflight,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_BRANCH_REF,
    M336K2CommittedFreezeAttestation,
    M336K2FreezeManifest,
    M336K2ProtocolError,
    m336k2_minimal_environment,
    validate_count_neutral_pool,
    verify_complete_freeze,
)
from ai_brain.stage3.acquisition.m336k_acquisition import (
    CandidateAcquisitionOutcome,
    M336KAcquisitionLedger,
    M336KAcquisitionLedgerReceipt,
    M336KGlobalAcquisitionReceipt,
    build_global_acquisition_receipt,
)
from ai_brain.stage3.acquisition.m336k_archive import ArchiveInspectionPolicyV2
from ai_brain.stage3.acquisition.m336k_final_pipeline import (
    m336k_candidate_terminal_policy,
    m336k_global_continuation_policy,
)

M336K2_FINAL_ACQUISITION_RUN_ID = "m336k2.final-java.global-acquisition.v1"


@dataclass(frozen=True)
class M336K2FinalAuthorization:
    schema_version: int
    contract_role: str
    execution_mode: str
    exact_implementation_tip: str
    exact_q28_sha: str
    branch_ref: str
    acquisition_run_id: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    archive_policy_hash: str
    candidate_terminal_policy_hash: str
    global_continuation_policy_hash: str
    route_manifest_hash: str
    route_registry_hash: str
    schema_registry_hash: str
    readiness_hash: str
    executable_dependency_manifest_hash: str
    python_environment_manifest_hash: str
    authority_statement_hash: str
    disclosure_registry_manifest_hash: str
    allowed_network_hosts: tuple[str, ...]
    minimum_candidate_families: int
    minimum_organizations: int
    maximum_candidates_per_organization: int
    acquisition_reservation_limit: int
    selector_reservation_limit: int
    evaluator_reservation_limit: int
    candidate_retry_limit: int
    candidate_replacement_limit: int
    pre_freeze_source_body_bytes: int
    authorization_hash: str


@dataclass(frozen=True)
class M336K2AcquisitionResult:
    preflight: FreshAcquisitionPreflight
    candidate_outcomes: tuple[CandidateAcquisitionOutcome, ...]
    global_receipt: M336KGlobalAcquisitionReceipt
    ledger_receipt: M336KAcquisitionLedgerReceipt
    public_receipt: dict


def build_m336k2_final_authorization(**values) -> M336K2FinalAuthorization:
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_FINAL_ACQUISITION_AUTHORIZATION_V1",
        **values,
    }
    result = M336K2FinalAuthorization(**body, authorization_hash=content_hash(body))
    verify_m336k2_final_authorization(result)
    return result


def authorization_from_dict(value: dict) -> M336K2FinalAuthorization:
    if set(value) != set(M336K2FinalAuthorization.__dataclass_fields__):
        raise M336K2ProtocolError("M336K2 authorization fields changed")
    result = M336K2FinalAuthorization(
        **{**value, "allowed_network_hosts": tuple(value["allowed_network_hosts"])}
    )
    verify_m336k2_final_authorization(result)
    return result


def verify_m336k2_final_authorization(value: M336K2FinalAuthorization) -> None:
    body = asdict(value)
    claimed = body.pop("authorization_hash")
    hashes = (
        value.candidate_pool_hash,
        value.acquisition_policy_hash,
        value.archive_policy_hash,
        value.candidate_terminal_policy_hash,
        value.global_continuation_policy_hash,
        value.route_manifest_hash,
        value.route_registry_hash,
        value.schema_registry_hash,
        value.readiness_hash,
        value.executable_dependency_manifest_hash,
        value.python_environment_manifest_hash,
        value.authority_statement_hash,
        value.disclosure_registry_manifest_hash,
    )
    final_mode = value.execution_mode == "FINAL"
    if (
        value.schema_version != 1
        or value.contract_role != "M336K2_FINAL_ACQUISITION_AUTHORIZATION_V1"
        or value.execution_mode not in {"REHEARSAL", "FINAL"}
        or (final_mode and value.acquisition_run_id != M336K2_FINAL_ACQUISITION_RUN_ID)
        or (
            not final_mode
            and value.acquisition_run_id == M336K2_FINAL_ACQUISITION_RUN_ID
        )
        or (final_mode and value.branch_ref != M336K2_BRANCH_REF)
        or (
            not final_mode
            and (
                value.branch_ref == M336K2_BRANCH_REF
                or not value.branch_ref.startswith("refs/heads/")
            )
        )
        or len(value.exact_implementation_tip) != 40
        or len(value.exact_q28_sha) != 40
        or any(len(item) != 64 for item in hashes)
        or tuple(sorted(set(value.allowed_network_hosts)))
        != value.allowed_network_hosts
        or not value.allowed_network_hosts
        or value.minimum_candidate_families < 80
        or value.minimum_organizations < 64
        or value.maximum_candidates_per_organization > 2
        or value.acquisition_reservation_limit != 1
        or value.selector_reservation_limit != 1
        or value.evaluator_reservation_limit != 1
        or value.candidate_retry_limit != 0
        or value.candidate_replacement_limit != 0
        or value.pre_freeze_source_body_bytes != 0
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 final authorization is invalid")


def validate_m336k2_candidate_pool(pool: dict) -> tuple[dict, ...]:
    if not isinstance(pool, dict):
        raise TypeError("M336K2 candidate pool must be an object")
    body = dict(pool)
    claimed = body.pop("pool_hash", None)
    candidates = tuple(pool.get("candidates", ()))
    organizations = Counter(item.get("organization_id") for item in candidates)
    if (
        content_hash(body) != claimed
        or pool.get("schema_version") != 1
        or pool.get("contract_role") != "M336K2_METADATA_ONLY_CANDIDATE_POOL"
        or pool.get("candidate_count") != len(candidates)
        or pool.get("organization_count") != len(organizations)
        or pool.get("maximum_candidates_per_organization")
        != max(organizations.values(), default=0)
        or pool.get("pre_freeze_source_body_bytes") != 0
        or pool.get("claims_final_eligibility") is not False
    ):
        raise M336K2ProtocolError("M336K2 metadata-only candidate pool is invalid")
    validate_count_neutral_pool(
        candidates,
        minimum_families=80,
        minimum_organizations=64,
        maximum_per_organization=2,
    )
    family_ids = tuple(item.get("family_id") for item in candidates)
    if family_ids != tuple(sorted(family_ids, key=lambda item: item.encode("utf-8"))):
        raise M336K2ProtocolError("M336K2 candidate pool ordering changed")
    required = {
        "family_id",
        "organization_id",
        "coordinate",
        "source_url",
        "pom_url",
        "scm_repository",
        "scm_commit",
        "source_content_length",
        "metadata_authority",
        "metadata_compilation_risk",
        "metadata_receipt_hashes",
        "repository_source_prefixes",
        "pom_license_declarations",
        "requirement",
        "policy_hash",
    }
    for item in candidates:
        candidate_body = dict(item)
        policy_hash = candidate_body.pop("policy_hash", None)
        source = urllib.parse.urlsplit(str(item.get("source_url", "")))
        pom = urllib.parse.urlsplit(str(item.get("pom_url", "")))
        scm = urllib.parse.urlsplit(str(item.get("scm_repository", "")))
        if (
            not required.issubset(item)
            or content_hash(candidate_body) != policy_hash
            or item["source_content_length"] <= 0
            or source.scheme != "https"
            or pom.scheme != "https"
            or scm.scheme != "https"
            or source.hostname is None
            or pom.hostname is None
            or scm.hostname is None
            or len(str(item["scm_commit"])) < 7
        ):
            raise M336K2ProtocolError("M336K2 candidate metadata policy is invalid")
    return candidates


def run_m336k2_frozen_acquisition(
    *,
    repository: Path,
    git_executable: Path,
    exact_f28_sha: str,
    freeze_root: Path,
    freeze_manifest: M336K2FreezeManifest,
    committed_attestation: M336K2CommittedFreezeAttestation,
    pool: dict,
    authorization: M336K2FinalAuthorization,
    acquisition_policy: dict,
    authority_statement: Path,
    disclosure_registry_manifest: Path,
    vault_root: Path,
    ledger: M336KAcquisitionLedger,
    private_preflight_path: Path,
    unused_selected_source_output: Path,
    host: str,
    maven_provider=None,
    scm_provider=None,
    acquire_one=None,
) -> M336K2AcquisitionResult:
    """Spend the M336K2 acquisition once after independent full-freeze checks."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    freeze_roots = {
        Path(item).parent.as_posix()
        for item in freeze_manifest.self_reference_safe_exclusions
    }
    try:
        supplied_freeze_root = (
            freeze_root.resolve(strict=True).relative_to(root).as_posix()
        )
    except ValueError as error:
        raise M336K2ProtocolError("M336K2 freeze root is outside repository") from error
    if freeze_roots != {supplied_freeze_root}:
        raise M336K2ProtocolError("M336K2 freeze root handle changed")
    verify_complete_freeze(root, freeze_manifest, allow_prospective_f28=True)
    verify_m336k2_final_authorization(authorization)
    _verify_attestation(exact_f28_sha, freeze_manifest, committed_attestation)
    _require_clean_exact_lineage(
        root,
        git,
        exact_f28_sha,
        authorization.exact_q28_sha,
        authorization.branch_ref,
    )
    candidates = validate_m336k2_candidate_pool(pool)
    _verify_inputs(
        candidates,
        pool,
        authorization,
        acquisition_policy,
        repository=root,
        authority_statement=authority_statement,
        disclosure_registry_manifest=disclosure_registry_manifest,
    )
    if ledger.events() or vault_root.exists() or private_preflight_path.exists():
        raise M336K2ProtocolError("M336K2 acquisition destinations are not fresh")
    context_hash = content_hash(
        (exact_f28_sha, authorization.authorization_hash, pool["pool_hash"])
    )
    outcomes: list[CandidateAcquisitionOutcome] = []
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
        operation_hash=pool["pool_hash"],
    )

    def terminal(outcome: CandidateAcquisitionOutcome) -> None:
        outcomes.append(outcome)

    def all_terminal() -> None:
        actual = tuple(item.terminal_receipt.candidate_family_id for item in outcomes)
        expected = tuple(item["family_id"] for item in candidates)
        if actual != expected or len(actual) != len(set(actual)):
            raise M336K2ProtocolError("M336K2 terminal accounting mismatch")
        ledger.append(
            "ALL_CANDIDATES_TERMINAL",
            context_hash=context_hash,
            operation_hash=content_hash(
                tuple(item.terminal_receipt.receipt_hash for item in outcomes)
            ),
        )

    try:
        unused_legacy = RunProtocolLedger(
            private_preflight_path.with_name("unused-legacy-ledger.jsonl"),
            git_worktrees=(root,),
        )
        preflight = run_fresh_acquisition_and_preflight(
            pool=pool,
            vault_root=vault_root,
            authority_statement=authority_statement,
            f20_sha=exact_f28_sha,
            timestamp="1970-01-01T00:00:00Z",
            host=host,
            ledger=unused_legacy,
            selected_source_output=unused_selected_source_output,
            git_worktrees=(root,),
            maven_provider=maven_provider,
            scm_provider=scm_provider,
            acquire_one=acquire_one,
            validate_pool=validate_m336k2_candidate_pool,
            record_protocol=False,
            perform_selector=False,
            acquisition_run_id=authorization.acquisition_run_id,
            candidate_outcome_callback=terminal,
            all_candidates_terminal_callback=all_terminal,
            target_file_count=acquisition_policy["selector_target_file_count"],
            maximum_files_per_root=acquisition_policy[
                "maximum_selected_files_per_root"
            ],
            minimum_root_count=acquisition_policy["minimum_selected_root_count"],
            construct_quotas=_construct_quota_pairs(
                acquisition_policy["construct_quotas"]
            ),
            selector_seed=acquisition_policy["selector_seed"],
            selector_version=acquisition_policy["selector_version"],
        )
        private_preflight_path.parent.mkdir(parents=True, exist_ok=True)
        private_preflight_path.write_text(
            canonical_json(asdict(preflight)) + "\n", encoding="utf-8", newline="\n"
        )
        for name, value in (
            ("candidate_qualification.json", preflight.qualification_report),
            (
                "source_entry_binding_manifest.json",
                asdict(preflight.source_entry_binding_manifest),
            ),
            ("selectability_census.json", asdict(preflight.selectability_census)),
            (
                "compilation_closure_feasibility.json",
                asdict(preflight.feasibility_proof),
            ),
            (
                "portable_vault_manifest.json",
                asdict(preflight.portable_vault_manifest),
            ),
        ):
            private_preflight_path.with_name(name).write_text(
                canonical_json(value) + "\n", encoding="utf-8", newline="\n"
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
            operation_hash=content_hash((type(error).__name__, str(error))),
        )
        raise
    ledger_receipt = ledger.receipt()
    status_counts = Counter(
        item.terminal_receipt.terminal_status.value for item in outcomes
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_FINAL_ACQUISITION_RECEIPT",
        "exact_f28_sha": exact_f28_sha,
        "authorization_hash": authorization.authorization_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "candidate_count": len(candidates),
        "terminal_count": len(outcomes),
        "terminal_status_counts": tuple(sorted(status_counts.items())),
        "missing_terminal_count": global_receipt.missing_terminal_count,
        "duplicate_terminal_count": global_receipt.duplicate_terminal_count,
        "candidate_retry_count": global_receipt.candidate_retry_count,
        "candidate_replacement_count": global_receipt.candidate_replacement_count,
        "vault_manifest_hash": global_receipt.vault_manifest_hash,
        "ledger_receipt_hash": ledger_receipt.receipt_hash,
        "status": "ACQUISITION_COMPLETED",
    }
    public = {**body, "receipt_hash": content_hash(body)}
    return M336K2AcquisitionResult(
        preflight=preflight,
        candidate_outcomes=tuple(outcomes),
        global_receipt=global_receipt,
        ledger_receipt=ledger_receipt,
        public_receipt=public,
    )


def _construct_quota_pairs(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list):
        raise M336K2ProtocolError("M336K2 construct quotas are invalid")
    rows = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], int)
            or isinstance(item[1], bool)
        ):
            raise M336K2ProtocolError("M336K2 construct quotas are invalid")
        rows.append((item[0], item[1]))
    return tuple(rows)


def _verify_attestation(
    exact_f28_sha: str,
    freeze: M336K2FreezeManifest,
    attestation: M336K2CommittedFreezeAttestation,
) -> None:
    body = asdict(attestation)
    claimed = body.pop("attestation_hash")
    if (
        attestation.status != "PASS"
        or attestation.exact_f28_sha != exact_f28_sha
        or attestation.exact_q28_parent != freeze.exact_q28_sha
        or attestation.prospective_freeze_tree_hash
        != freeze.prospective_freeze_tree_hash
        or attestation.authorization_hash != freeze.authorization_hash
        or attestation.route_hash != freeze.route_hash
        or attestation.implementation_change_count != 0
        or attestation.merge_count != 0
        or not attestation.prospective_tree_matches
        or not attestation.head_upstream_remote_equal
        or not attestation.worktree_clean
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 committed freeze attestation changed")


def _verify_inputs(
    candidates,
    pool,
    authorization,
    acquisition_policy,
    *,
    repository: Path,
    authority_statement: Path,
    disclosure_registry_manifest: Path,
) -> None:
    policy_body = dict(acquisition_policy)
    claimed = policy_body.pop("acquisition_policy_hash", None)
    terminal = m336k_candidate_terminal_policy()
    continuation = m336k_global_continuation_policy()
    archive = ArchiveInspectionPolicyV2.frozen_default()
    hosts = tuple(
        sorted(
            {
                parsed.hostname
                for item in candidates
                for key in (
                    "source_url",
                    "pom_url",
                    "scm_repository",
                    "scm_archive_head_url",
                )
                if (parsed := urllib.parse.urlsplit(str(item.get(key, "")))).hostname
            }
        )
    )
    if (
        content_hash(policy_body) != claimed
        or claimed != authorization.acquisition_policy_hash
        or acquisition_policy.get("policy_version")
        != "m336k2.candidate-isolated-final.v1"
        or acquisition_policy.get("acquisition_run_id")
        != authorization.acquisition_run_id
        or acquisition_policy.get("candidate_pool_hash") != pool["pool_hash"]
        or acquisition_policy.get("archive_policy_hash") != archive.policy_hash
        or acquisition_policy.get("candidate_terminal_policy_hash")
        != terminal["policy_hash"]
        or acquisition_policy.get("global_continuation_policy_hash")
        != continuation["policy_hash"]
        or tuple(acquisition_policy.get("allowed_network_hosts", ())) != hosts
        or authorization.allowed_network_hosts != hosts
        or authorization.candidate_pool_hash != pool["pool_hash"]
        or authorization.archive_policy_hash != archive.policy_hash
        or authorization.candidate_terminal_policy_hash != terminal["policy_hash"]
        or authorization.global_continuation_policy_hash != continuation["policy_hash"]
        or bytes_hash(authority_statement.resolve(strict=True).read_bytes())
        != authorization.authority_statement_hash
        or bytes_hash(disclosure_registry_manifest.resolve(strict=True).read_bytes())
        != authorization.disclosure_registry_manifest_hash
        or bytes_hash(
            (
                repository
                / "artifacts"
                / "acquisition"
                / "disclosed_java"
                / "registry_manifest.json"
            )
            .resolve(strict=True)
            .read_bytes()
        )
        != authorization.disclosure_registry_manifest_hash
        or acquisition_policy.get("authority_statement_hash")
        != authorization.authority_statement_hash
        or acquisition_policy.get("disclosure_registry_manifest_hash")
        != authorization.disclosure_registry_manifest_hash
        or acquisition_policy.get("acquisition_reservation_limit") != 1
        or acquisition_policy.get("candidate_retry_limit") != 0
        or acquisition_policy.get("candidate_replacement_limit") != 0
        or acquisition_policy.get("pre_freeze_source_body_bytes") != 0
        or not isinstance(acquisition_policy.get("selector_target_file_count"), int)
        or acquisition_policy.get("selector_target_file_count", 0) <= 0
        or not isinstance(
            acquisition_policy.get("maximum_selected_files_per_root"), int
        )
        or acquisition_policy.get("maximum_selected_files_per_root", 0) <= 0
        or not isinstance(acquisition_policy.get("minimum_selected_root_count"), int)
        or acquisition_policy.get("minimum_selected_root_count", 0) < 3
        or not isinstance(acquisition_policy.get("construct_quotas"), list)
        or not acquisition_policy.get("selector_seed")
        or not acquisition_policy.get("selector_version")
    ):
        raise M336K2ProtocolError("M336K2 acquisition inputs are inconsistent")


def _require_clean_exact_lineage(
    repository: Path,
    git: Path,
    expected_head: str,
    expected_parent: str,
    expected_branch_ref: str,
) -> None:
    head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    parent = _git(git, repository, "rev-parse", "HEAD^1")
    branch = _git(git, repository, "symbolic-ref", "HEAD")
    status = _git(git, repository, "status", "--porcelain=v1")
    merges = _git(
        git,
        repository,
        "rev-list",
        "--merges",
        "--count",
        f"{expected_parent}..{expected_head}",
    )
    if (
        head != expected_head
        or parent != expected_parent
        or branch != expected_branch_ref
        or status
        or merges != "0"
    ):
        raise M336K2ProtocolError("M336K2 acquisition requires clean exact F28")


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()
