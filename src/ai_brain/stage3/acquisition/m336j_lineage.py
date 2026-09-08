"""Git-object-derived implementation lineage authority for M-33.6j."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash

M336J_EXACT_F24_SHA = "4891de1c3a0f6ba2d5d012ab5189dbb5222ba6bd"
M336J_EXACT_R25A_SHA = "b05ac235b291acbb514cb8256302610964042d3f"
M336J_EXACT_R25B_SHA = "40b8a306ef6f8cf0f2f70a8cc3e272ef11846a42"
M336J_BRANCH_NAME = "exp/stage3-m336j-hermetic-karina-final-java-v9"
M336J_UPSTREAM_REF = f"origin/{M336J_BRANCH_NAME}"
M336J_R25A_SUBJECT = "M-33.6j close hermetic Karina execution environment"
M336J_R25B_SUBJECT = "M-33.6j complete hermetic route qualification implementation"
M336J_R25C_SUBJECT = "M-33.6j repair linear readiness ancestry verification"
M336J_GIT_LINEAGE_LAYER = "GIT_LINEAGE_VERIFICATION"


class M336JGitLineageError(ValueError):
    """A failure derived at the Git lineage authority layer."""


@dataclass(frozen=True)
class M336JImplementationCommit:
    commit_sha: str
    parent_sha: str
    subject_hash: str


@dataclass(frozen=True)
class M336JImplementationLineagePolicy:
    schema_version: int
    contract_role: str
    exact_base_f24_sha: str
    exact_r25a_sha: str
    exact_r25b_sha: str
    current_implementation_head_sha: str
    expected_implementation_commit_count: int
    no_merge_required: bool
    first_parent_required: bool
    expected_subject_hashes: tuple[str, ...]
    expected_branch_name: str | None
    expected_upstream_ref: str | None
    policy_hash: str


@dataclass(frozen=True)
class M336JImplementationLineageReceipt:
    schema_version: int
    contract_role: str
    base_sha: str
    policy_hash: str
    ordered_implementation_shas: tuple[str, ...]
    parent_rows: tuple[M336JImplementationCommit, ...]
    commit_subject_hashes: tuple[str, ...]
    merge_count: int
    extra_commit_count: int
    missing_commit_count: int
    order_mismatch_count: int
    subject_mismatch_count: int
    status: str
    receipt_hash: str


def build_m336j_implementation_lineage_policy(
    current_implementation_head_sha: str,
) -> M336JImplementationLineagePolicy:
    """Bind immutable history and the request-supplied R25c identity."""

    return build_implementation_lineage_policy(
        exact_base_f24_sha=M336J_EXACT_F24_SHA,
        exact_r25a_sha=M336J_EXACT_R25A_SHA,
        exact_r25b_sha=M336J_EXACT_R25B_SHA,
        current_implementation_head_sha=current_implementation_head_sha,
        expected_subjects=(
            M336J_R25A_SUBJECT,
            M336J_R25B_SUBJECT,
            M336J_R25C_SUBJECT,
        ),
        expected_branch_name=M336J_BRANCH_NAME,
        expected_upstream_ref=M336J_UPSTREAM_REF,
    )


def build_implementation_lineage_policy(
    *,
    exact_base_f24_sha: str,
    exact_r25a_sha: str,
    exact_r25b_sha: str,
    current_implementation_head_sha: str,
    expected_subjects: tuple[str, str, str],
    expected_branch_name: str | None = None,
    expected_upstream_ref: str | None = None,
) -> M336JImplementationLineagePolicy:
    shas = (
        exact_base_f24_sha,
        exact_r25a_sha,
        exact_r25b_sha,
        current_implementation_head_sha,
    )
    if any(not _is_git_sha(item) for item in shas) or len(set(shas)) != len(shas):
        _fail("lineage policy contains an invalid or repeated Git identity")
    if any(not isinstance(item, str) or not item for item in expected_subjects):
        _fail("lineage policy contains an invalid expected subject")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_IMPLEMENTATION_LINEAGE_POLICY",
        "exact_base_f24_sha": exact_base_f24_sha,
        "exact_r25a_sha": exact_r25a_sha,
        "exact_r25b_sha": exact_r25b_sha,
        "current_implementation_head_sha": current_implementation_head_sha,
        "expected_implementation_commit_count": 3,
        "no_merge_required": True,
        "first_parent_required": True,
        "expected_subject_hashes": tuple(
            content_hash(item) for item in expected_subjects
        ),
        "expected_branch_name": expected_branch_name,
        "expected_upstream_ref": expected_upstream_ref,
    }
    return M336JImplementationLineagePolicy(**body, policy_hash=content_hash(body))


def implementation_lineage_policy_from_dict(
    value: dict,
) -> M336JImplementationLineagePolicy:
    if not isinstance(value, dict) or set(value) != {
        item.name for item in fields(M336JImplementationLineagePolicy)
    }:
        _fail("lineage policy fields changed")
    converted = dict(value)
    subjects = converted.get("expected_subject_hashes")
    if not isinstance(subjects, list):
        _fail("lineage policy subject hashes are not a strict array")
    converted["expected_subject_hashes"] = tuple(subjects)
    policy = M336JImplementationLineagePolicy(**converted)
    _verify_policy(policy)
    return policy


def implementation_lineage_receipt_from_dict(
    value: dict,
) -> M336JImplementationLineageReceipt:
    if not isinstance(value, dict) or set(value) != {
        item.name for item in fields(M336JImplementationLineageReceipt)
    }:
        _fail("lineage receipt fields changed")
    converted = dict(value)
    shas = converted.get("ordered_implementation_shas")
    subjects = converted.get("commit_subject_hashes")
    rows = converted.get("parent_rows")
    if (
        not isinstance(shas, list)
        or not isinstance(subjects, list)
        or not isinstance(rows, list)
    ):
        _fail("lineage receipt arrays changed")
    converted["ordered_implementation_shas"] = tuple(shas)
    converted["commit_subject_hashes"] = tuple(subjects)
    try:
        converted["parent_rows"] = tuple(
            M336JImplementationCommit(**row)
            for row in rows
            if isinstance(row, dict)
            and set(row) == {item.name for item in fields(M336JImplementationCommit)}
        )
    except TypeError as error:
        raise M336JGitLineageError(
            f"{M336J_GIT_LINEAGE_LAYER}: lineage parent rows changed"
        ) from error
    if len(converted["parent_rows"]) != len(rows):
        _fail("lineage parent rows changed")
    receipt = M336JImplementationLineageReceipt(**converted)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if (
        receipt.status != "PASS"
        or content_hash(body) != claimed
        or receipt.ordered_implementation_shas
        != tuple(row.commit_sha for row in receipt.parent_rows)
        or receipt.commit_subject_hashes
        != tuple(row.subject_hash for row in receipt.parent_rows)
    ):
        _fail("lineage receipt is not content-derived")
    return receipt


def verify_m336j_implementation_lineage(
    repository: Path,
    git_executable: Path,
    policy: M336JImplementationLineagePolicy,
) -> M336JImplementationLineageReceipt:
    """Derive the exact ordered lineage from live Git objects."""

    try:
        _verify_policy(policy)
        root = repository.resolve(strict=True)
        git = git_executable.resolve(strict=True)
        head = _git(git, root, "rev-parse", "HEAD^{commit}")
        if head != policy.current_implementation_head_sha:
            _fail("request SHA differs from live HEAD")
        if _git(git, root, "rev-parse", "--is-shallow-repository") != "false":
            _fail("shallow or incomplete history is not authoritative")
        ancestor = _git_result(
            git,
            root,
            "merge-base",
            "--is-ancestor",
            policy.exact_base_f24_sha,
            head,
        )
        if ancestor.returncode != 0:
            _fail("F24 is not an ancestor of the implementation HEAD")
        actual = tuple(
            line
            for line in _git(
                git,
                root,
                "rev-list",
                "--first-parent",
                "--reverse",
                f"{policy.exact_base_f24_sha}..{head}",
            ).splitlines()
            if line
        )
        expected = (
            policy.exact_r25a_sha,
            policy.exact_r25b_sha,
            policy.current_implementation_head_sha,
        )
        missing_count = len(set(expected) - set(actual))
        extra_count = len(set(actual) - set(expected))
        order_mismatch_count = sum(
            left != right for left, right in zip(actual, expected, strict=False)
        ) + abs(len(actual) - len(expected))
        merge_count = int(
            _git(
                git,
                root,
                "rev-list",
                "--count",
                "--merges",
                f"{policy.exact_base_f24_sha}..{head}",
            )
        )
        rows = tuple(_commit_row(git, root, commit) for commit in actual)
        expected_parents = (
            policy.exact_base_f24_sha,
            policy.exact_r25a_sha,
            policy.exact_r25b_sha,
        )
        parent_mismatch_count = sum(
            row.parent_sha != expected_parent
            for row, expected_parent in zip(rows, expected_parents, strict=False)
        ) + abs(len(rows) - len(expected_parents))
        subject_hashes = tuple(row.subject_hash for row in rows)
        subject_mismatch_count = sum(
            actual_hash != expected_hash
            for actual_hash, expected_hash in zip(
                subject_hashes, policy.expected_subject_hashes, strict=False
            )
        ) + abs(len(subject_hashes) - len(policy.expected_subject_hashes))
        if policy.expected_branch_name is not None:
            branch = _git(git, root, "symbolic-ref", "--short", "HEAD")
            if branch != policy.expected_branch_name:
                _fail("checked-out branch differs from the lineage policy")
        if policy.expected_upstream_ref is not None:
            upstream = _git(
                git,
                root,
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            )
            upstream_head = _git(git, root, "rev-parse", "@{upstream}^{commit}")
            if upstream != policy.expected_upstream_ref or upstream_head != head:
                _fail("upstream state differs from the lineage policy")
        status = _git(git, root, "status", "--porcelain=v1")
        if status:
            _fail("repository worktree is dirty")
        if (
            actual != expected
            or len(rows) != policy.expected_implementation_commit_count
            or merge_count
            or missing_count
            or extra_count
            or order_mismatch_count
            or parent_mismatch_count
            or subject_mismatch_count
        ):
            _fail("live Git objects differ from the exact implementation lineage")
        body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336J_IMPLEMENTATION_LINEAGE_RECEIPT",
            "base_sha": policy.exact_base_f24_sha,
            "policy_hash": policy.policy_hash,
            "ordered_implementation_shas": actual,
            "parent_rows": rows,
            "commit_subject_hashes": subject_hashes,
            "merge_count": merge_count,
            "extra_commit_count": extra_count,
            "missing_commit_count": missing_count,
            "order_mismatch_count": order_mismatch_count,
            "subject_mismatch_count": subject_mismatch_count,
            "status": "PASS",
        }
        return M336JImplementationLineageReceipt(
            **body, receipt_hash=content_hash(body)
        )
    except M336JGitLineageError:
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise M336JGitLineageError(
            f"{M336J_GIT_LINEAGE_LAYER}: Git object verification failed"
        ) from error


def verify_supplied_implementation_lineage_receipt(
    repository: Path,
    git_executable: Path,
    policy: M336JImplementationLineagePolicy,
    supplied: M336JImplementationLineageReceipt,
) -> M336JImplementationLineageReceipt:
    """Reject a content-rehashed claim unless it equals live Git derivation."""

    derived = verify_m336j_implementation_lineage(repository, git_executable, policy)
    if supplied != derived:
        _fail("supplied lineage receipt differs from live Git derivation")
    return derived


def _verify_policy(policy: M336JImplementationLineagePolicy) -> None:
    if not isinstance(policy, M336JImplementationLineagePolicy):
        _fail("lineage policy must be typed")
    body = asdict(policy)
    claimed = body.pop("policy_hash")
    shas = (
        policy.exact_base_f24_sha,
        policy.exact_r25a_sha,
        policy.exact_r25b_sha,
        policy.current_implementation_head_sha,
    )
    if (
        policy.schema_version != 1
        or policy.contract_role != "PUBLIC_SAFE_M336J_IMPLEMENTATION_LINEAGE_POLICY"
        or policy.expected_implementation_commit_count != 3
        or not policy.no_merge_required
        or not policy.first_parent_required
        or len(policy.expected_subject_hashes) != 3
        or any(not _is_hash(item) for item in policy.expected_subject_hashes)
        or any(not _is_git_sha(item) for item in shas)
        or len(set(shas)) != len(shas)
        or content_hash(body) != claimed
    ):
        _fail("lineage policy is not content-derived")


def _commit_row(
    git: Path, repository: Path, commit_sha: str
) -> M336JImplementationCommit:
    tokens = _git(
        git, repository, "rev-list", "--parents", "-n", "1", commit_sha
    ).split()
    if len(tokens) != 2 or tokens[0] != commit_sha:
        _fail("implementation commit does not have exactly one parent")
    subject = _git(git, repository, "show", "-s", "--format=%s", commit_sha)
    return M336JImplementationCommit(
        commit_sha=commit_sha,
        parent_sha=tokens[1],
        subject_hash=content_hash(subject),
    )


def _git(git: Path, repository: Path, *arguments: str) -> str:
    result = _git_result(git, repository, *arguments)
    if result.returncode != 0:
        _fail("Git command failed while deriving lineage")
    return result.stdout.strip()


def _git_result(
    git: Path, repository: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _is_git_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(item in "0123456789abcdef" for item in value)
    )


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(item in "0123456789abcdef" for item in value)
    )


def _fail(message: str) -> None:
    raise M336JGitLineageError(f"{M336J_GIT_LINEAGE_LAYER}: {message}")
