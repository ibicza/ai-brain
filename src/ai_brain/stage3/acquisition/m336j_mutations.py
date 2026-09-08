"""Canonical mutation evidence for the M-33.6j hermetic route."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.facts.canonical import content_hash

M336J_MUTATIONS = (
    "uv_absent_from_path",
    "path_completely_minimal",
    "profile_unavailable",
    "bashrc_unavailable",
    "wrong_direct_python_path",
    "changed_python_binary",
    "changed_python_version",
    "changed_environment_package_manifest",
    "changed_uv_lock",
    "changed_project_source_identity",
    "wrong_git_binary",
    "wrong_git_version",
    "wrong_javac",
    "wrong_java",
    "wrong_shell_binary",
    "capsule_path_moved_after_receipt",
    "executable_symlink_retargeted",
    "remote_token_contains_space",
    "remote_token_contains_quote",
    "remote_token_contains_semicolon",
    "remote_token_contains_command_substitution",
    "remote_token_contains_newline",
    "repository_path_contains_spaces",
    "private_root_contains_spaces",
    "wrong_ssh_host_key",
    "wrong_karina_host_identity",
    "dirty_karina_worktree",
    "wrong_remote_head",
    "missing_project_import",
    "uv_attempts_environment_sync",
    "uv_attempts_network_fallback",
    "bare_uv_reintroduced",
    "bare_python_reintroduced",
    "bare_git_reintroduced",
    "unregistered_ssh_subprocess_reintroduced",
    "response_request_hash_mismatch",
    "response_component_binding_mismatch",
    "response_host_identity_mismatch",
    "worker_request_replayed_for_another_run",
    "worker_request_replayed_for_another_freeze",
    "insufficient_disk_space",
    "archive_larger_than_bound",
    "truncated_streamed_archive",
    "streamed_archive_hash_mismatch",
    "duplicate_archive_entry",
    "schema_hash_codec_mismatch",
    "cross_route_run_response",
    "cross_host_response",
    "cross_candidate_pack_response",
    "evaluation_before_production",
    "large_in_memory_helper_over_limit",
)
M336J_ROBUST_PASS_MUTATIONS = frozenset(
    {
        "uv_absent_from_path",
        "path_completely_minimal",
        "profile_unavailable",
        "bashrc_unavailable",
        "remote_token_contains_space",
        "remote_token_contains_quote",
        "remote_token_contains_semicolon",
        "remote_token_contains_command_substitution",
        "repository_path_contains_spaces",
        "private_root_contains_spaces",
    }
)
M336J_MUTATION_VALIDATOR_CLASSES = {
    mutation_id: (
        "EXECUTION_CAPSULE_VERIFIER"
        if mutation_id
        in {
            "wrong_direct_python_path",
            "changed_python_binary",
            "changed_python_version",
            "changed_environment_package_manifest",
            "changed_uv_lock",
            "changed_project_source_identity",
            "wrong_git_binary",
            "wrong_git_version",
            "wrong_javac",
            "wrong_java",
            "wrong_shell_binary",
            "capsule_path_moved_after_receipt",
            "executable_symlink_retargeted",
            "missing_project_import",
        }
        else "COMMAND_PLAN_BUILDER"
        if mutation_id
        in {
            "uv_absent_from_path",
            "path_completely_minimal",
            "profile_unavailable",
            "bashrc_unavailable",
            "remote_token_contains_space",
            "remote_token_contains_quote",
            "remote_token_contains_semicolon",
            "remote_token_contains_command_substitution",
            "remote_token_contains_newline",
            "repository_path_contains_spaces",
            "private_root_contains_spaces",
            "uv_attempts_environment_sync",
            "uv_attempts_network_fallback",
            "bare_uv_reintroduced",
            "bare_python_reintroduced",
            "bare_git_reintroduced",
            "unregistered_ssh_subprocess_reintroduced",
        }
        else "SSH_HOST_PREFLIGHT"
        if mutation_id
        in {
            "wrong_ssh_host_key",
            "wrong_karina_host_identity",
            "dirty_karina_worktree",
            "wrong_remote_head",
        }
        else "WORKER_REQUEST_VALIDATOR"
        if mutation_id
        in {
            "worker_request_replayed_for_another_run",
            "worker_request_replayed_for_another_freeze",
        }
        else "STORAGE_CAPACITY_VERIFIER"
        if mutation_id == "insufficient_disk_space"
        else "TREE_TRANSFER_VERIFIER"
        if mutation_id
        in {
            "archive_larger_than_bound",
            "truncated_streamed_archive",
            "streamed_archive_hash_mismatch",
            "duplicate_archive_entry",
            "large_in_memory_helper_over_limit",
        }
        else "STRICT_SCHEMA_LOADER"
        if mutation_id == "schema_hash_codec_mismatch"
        else "ROUTE_TRANSCRIPT_VERIFIER"
        if mutation_id
        in {
            "cross_route_run_response",
            "cross_host_response",
            "cross_candidate_pack_response",
            "evaluation_before_production",
        }
        else "RESPONSE_VERIFIER"
    )
    for mutation_id in M336J_MUTATIONS
}


@dataclass(frozen=True)
class M336JMutationResult:
    mutation_id: str
    validator_class: str
    failure_class: str | None
    failure_message_hash: str | None
    status: str
    result_hash: str


@dataclass(frozen=True)
class M336JMutationReport:
    schema_version: int
    contract_role: str
    mutations: tuple[M336JMutationResult, ...]
    executed_mutation_count: int
    fail_closed_mutation_count: int
    robust_pass_mutation_count: int
    rejected_mutation_count: int
    accepted_mutation_count: int
    wrong_rejection_layer_count: int
    final_acquisition_reservation_count: int
    status: str
    report_hash: str


def mutation_result(
    mutation_id: str,
    *,
    validator_class: str,
    failure: BaseException | None,
) -> M336JMutationResult:
    expected = (
        "ROBUST_PASS" if mutation_id in M336J_ROBUST_PASS_MUTATIONS else "FAIL_CLOSED"
    )
    if mutation_id not in M336J_MUTATIONS:
        raise ValueError("M336J mutation identifier is unknown")
    if validator_class != M336J_MUTATION_VALIDATOR_CLASSES[mutation_id]:
        raise ValueError("M336J mutation was checked at the wrong rejection layer")
    if (failure is None) != (expected == "ROBUST_PASS"):
        raise ValueError("M336J mutation did not exhibit the expected behavior")
    body = {
        "mutation_id": mutation_id,
        "validator_class": validator_class,
        "failure_class": type(failure).__name__ if failure is not None else None,
        "failure_message_hash": (
            content_hash(str(failure)) if failure is not None else None
        ),
        "status": expected,
    }
    return M336JMutationResult(**body, result_hash=content_hash(body))


def build_mutation_report(
    results: tuple[M336JMutationResult, ...],
    *,
    final_acquisition_reservation_count: int,
) -> M336JMutationReport:
    by_id = {item.mutation_id: item for item in results}
    if tuple(by_id) != M336J_MUTATIONS or len(by_id) != len(results):
        raise ValueError("M336J mutation matrix is incomplete or reordered")
    for item in results:
        body = asdict(item)
        claimed = body.pop("result_hash")
        expected = (
            "ROBUST_PASS"
            if item.mutation_id in M336J_ROBUST_PASS_MUTATIONS
            else "FAIL_CLOSED"
        )
        if content_hash(body) != claimed or item.status != expected:
            raise ValueError("M336J mutation result is invalid")
    fail_closed = sum(item.status == "FAIL_CLOSED" for item in results)
    robust = sum(item.status == "ROBUST_PASS" for item in results)
    body: dict[str, Any] = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_MUTATION_REPORT",
        "mutations": results,
        "executed_mutation_count": len(results),
        "fail_closed_mutation_count": fail_closed,
        "robust_pass_mutation_count": robust,
        "rejected_mutation_count": len(results),
        "accepted_mutation_count": 0,
        "wrong_rejection_layer_count": 0,
        "final_acquisition_reservation_count": final_acquisition_reservation_count,
        "status": "PASS",
    }
    if final_acquisition_reservation_count or len(results) != len(M336J_MUTATIONS):
        raise ValueError("M336J mutation gate touched final acquisition")
    return M336JMutationReport(**body, report_hash=content_hash(body))
