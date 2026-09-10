"""Independent exact-implementation readiness gate for M-33.6k.2."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_BRANCH,
    M336K2_READY_STATUS,
    M336K2ProtocolError,
    build_unspent_readiness_state,
    m336k2_minimal_environment,
)

M336K2_REQUIRED_READINESS_EVIDENCE = frozenset(
    {
        "windows_quality",
        "karina_quality",
        "r27_baseline",
        "implementation_tip_qualification",
        "cross_platform_comparator",
        "mutation_matrix",
        "executable_closure",
        "disposable_chain",
        "metadata_pool",
        "storage_preflight",
        "route_registry",
        "schema_registry",
        "publication_contracts",
        "commit_protocol",
        "source_leak_report",
    }
)


@dataclass(frozen=True)
class M336K2ReadinessEvidence:
    name: str
    path: Path
    hash_field: str
    expected_status: str


@dataclass(frozen=True)
class M336K2ReadinessResult:
    schema_version: int
    contract_role: str
    exact_implementation_tip: str
    branch: str
    upstream_sha: str
    remote_sha: str
    clean_worktree_count: int
    dirty_worktree_count: int
    evidence_hashes: tuple[tuple[str, str], ...]
    evidence_bytes_hashes: tuple[tuple[str, str], ...]
    final_destination_identity_hashes: tuple[tuple[str, str], ...]
    final_state_readiness_hash: str
    acquisition_reservations: int
    acquisition_invocations: int
    selector_reservations: int
    selector_invocations: int
    evaluator_reservations: int
    evaluator_invocations: int
    route_state_events: int
    final_candidate_source_body_bytes: int
    status: str
    readiness_hash: str


def build_m336k2_readiness(
    *,
    repository: Path,
    git_executable: Path,
    exact_implementation_tip: str,
    evidence: tuple[M336K2ReadinessEvidence, ...],
    final_destinations: dict[str, Path],
    expected_branch: str = M336K2_BRANCH,
) -> M336K2ReadinessResult:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    names = {item.name for item in evidence}
    if names != M336K2_REQUIRED_READINESS_EVIDENCE or len(names) != len(evidence):
        raise M336K2ProtocolError("M336K2 readiness evidence set changed")
    branch = _git(git, root, "symbolic-ref", "--short", "HEAD")
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote_row = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()
    remote = remote_row[0] if remote_row else ""
    if (
        branch != expected_branch
        or head != exact_implementation_tip
        or upstream != head
        or remote != head
    ):
        raise M336K2ProtocolError("M336K2 readiness lineage is not exact and pushed")
    worktrees = _worktrees(git, root)
    dirty = tuple(
        path for path in worktrees if _git(git, path, "status", "--porcelain=v1")
    )
    if dirty:
        raise M336K2ProtocolError("M336K2 readiness requires every worktree clean")
    evidence_hashes = []
    evidence_bytes = []
    for item in sorted(evidence, key=lambda value: value.name):
        value = _object(item.path.resolve(strict=True))
        body = dict(value)
        claimed = body.pop(item.hash_field, None)
        if (
            not isinstance(claimed, str)
            or content_hash(body) != claimed
            or value.get("status") != item.expected_status
        ):
            raise M336K2ProtocolError(
                f"M336K2 readiness evidence is invalid: {item.name}"
            )
        evidence_hashes.append((item.name, claimed))
        evidence_bytes.append((item.name, bytes_hash(item.path.read_bytes())))
    final_state = build_unspent_readiness_state(final_destinations)
    destination_identities = m336k2_destination_identity_hashes(final_destinations)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_Q28_READINESS",
        "exact_implementation_tip": exact_implementation_tip,
        "branch": branch,
        "upstream_sha": upstream,
        "remote_sha": remote,
        "clean_worktree_count": len(worktrees),
        "dirty_worktree_count": 0,
        "evidence_hashes": tuple(evidence_hashes),
        "evidence_bytes_hashes": tuple(evidence_bytes),
        "final_destination_identity_hashes": destination_identities,
        "final_state_readiness_hash": final_state.readiness_hash,
        "acquisition_reservations": final_state.acquisition_reservations,
        "acquisition_invocations": final_state.acquisition_invocations,
        "selector_reservations": final_state.selector_reservations,
        "selector_invocations": final_state.selector_invocations,
        "evaluator_reservations": final_state.evaluator_reservations,
        "evaluator_invocations": final_state.evaluator_invocations,
        "route_state_events": final_state.route_state_events,
        "final_candidate_source_body_bytes": (
            final_state.final_candidate_source_body_bytes
        ),
        "status": M336K2_READY_STATUS,
    }
    return M336K2ReadinessResult(**body, readiness_hash=content_hash(body))


def m336k2_destination_identity_hashes(
    destinations: dict[str, Path],
) -> tuple[tuple[str, str], ...]:
    """Return public-safe identities for the private one-shot destinations."""

    return tuple(
        sorted(
            (name, content_hash(path.resolve(strict=False).as_posix()))
            for name, path in destinations.items()
        )
    )


def verify_m336k2_readiness_destinations(
    readiness: M336K2ReadinessResult,
    destinations: dict[str, Path],
) -> None:
    if (
        readiness.final_destination_identity_hashes
        != m336k2_destination_identity_hashes(destinations)
    ):
        raise M336K2ProtocolError("M336K2 final destination handles changed")


def readiness_from_dict(value: dict) -> M336K2ReadinessResult:
    if set(value) != set(M336K2ReadinessResult.__dataclass_fields__):
        raise M336K2ProtocolError("M336K2 readiness fields changed")
    parsed = M336K2ReadinessResult(
        **{
            **value,
            "evidence_hashes": tuple(tuple(row) for row in value["evidence_hashes"]),
            "evidence_bytes_hashes": tuple(
                tuple(row) for row in value["evidence_bytes_hashes"]
            ),
            "final_destination_identity_hashes": tuple(
                tuple(row) for row in value["final_destination_identity_hashes"]
            ),
        }
    )
    body = asdict(parsed)
    claimed = body.pop("readiness_hash")
    evidence_names = {name for name, _hash in parsed.evidence_hashes}
    evidence_byte_names = {name for name, _hash in parsed.evidence_bytes_hashes}
    destination_names = {
        name for name, _hash in parsed.final_destination_identity_hashes
    }
    hashes = tuple(
        item
        for rows in (
            parsed.evidence_hashes,
            parsed.evidence_bytes_hashes,
            parsed.final_destination_identity_hashes,
        )
        for _name, item in rows
    )
    if (
        parsed.status != M336K2_READY_STATUS
        or parsed.contract_role != "PUBLIC_SAFE_M336K2_Q28_READINESS"
        or len(parsed.exact_implementation_tip) != 40
        or len(parsed.upstream_sha) != 40
        or len(parsed.remote_sha) != 40
        or parsed.upstream_sha != parsed.exact_implementation_tip
        or parsed.remote_sha != parsed.exact_implementation_tip
        or parsed.clean_worktree_count < 1
        or parsed.dirty_worktree_count != 0
        or evidence_names != M336K2_REQUIRED_READINESS_EVIDENCE
        or evidence_byte_names != M336K2_REQUIRED_READINESS_EVIDENCE
        or len(parsed.evidence_hashes) != len(evidence_names)
        or len(parsed.evidence_bytes_hashes) != len(evidence_byte_names)
        or destination_names
        != {
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
        or len(parsed.final_destination_identity_hashes) != len(destination_names)
        or any(len(item) != 64 for item in hashes)
        or any(
            (
                parsed.acquisition_reservations,
                parsed.acquisition_invocations,
                parsed.selector_reservations,
                parsed.selector_invocations,
                parsed.evaluator_reservations,
                parsed.evaluator_invocations,
                parsed.route_state_events,
                parsed.final_candidate_source_body_bytes,
            )
        )
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 readiness hash/status changed")
    return parsed


def _worktrees(git: Path, repository: Path) -> tuple[Path, ...]:
    raw = subprocess.run(
        (str(git), "worktree", "list", "--porcelain", "-z"),
        cwd=repository,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout
    prefix = b"worktree "
    return tuple(
        Path(field.removeprefix(prefix).decode("utf-8"))
        for field in raw.split(b"\0")
        if field.startswith(prefix)
    )


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 readiness input is not JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 readiness input is not an object")
    return value


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
