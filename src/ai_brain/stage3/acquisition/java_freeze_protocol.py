"""Static verifier for the future F13 -> H13 -> E13 Java freeze protocol."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_freeze_roles import (
    PROTECTED_FINAL_ROLES,
    build_final_artifact_role_manifest,
    classify_final_artifact_role,
    verify_role_aware_disclosure,
)

M344_FROZEN_PREFIXES = (
    ".gitattributes",
    "pyproject.toml",
    "schemas",
    "scripts",
    "src",
    "tests",
    "tools",
    "uv.lock",
)
M344_H13_PREFIXES = (
    "docs/m344_final_semantic_metrics.md",
    "docs/m344_final_source_inventory.md",
    "docs/m344_final_trust_metrics.md",
    "evaluation/m344_final_java",
)
M344_E13_PREFIXES = (
    "docs/m344_final_evidence_report.md",
    "docs/m344_fresh_java_freeze_report.md",
    "runs/m344_fresh_java_freeze_report.md",
    "runs/m344_fresh_java_freeze",
)
M344_COMMIT_MESSAGES = (
    "M-34.4 freeze oracle-free Java acquisition",
    "M-34.4 untouched real-Java evaluation",
    "M-34.4 exact-SHA fresh-freeze evidence",
)

M336_BASE_SHA = "6b0c31e6e6f987216923a66e332370aeeffa9f48"
M336_EXCLUDED_M33_SHA = "b94c17dc8b1026fe9e338b5fc0a4926b23d68a39"
M336_BRANCH = "exp/stage3-m336-fresh-java-freeze"
M336_FROZEN_PREFIXES = M344_FROZEN_PREFIXES
M336_H15_PREFIXES = (
    "docs/m336_final_semantic_metrics.md",
    "docs/m336_final_source_inventory.md",
    "docs/m336_final_trust_metrics.md",
    "docs/m336_runtime_proof.md",
    "evaluation/m336_final_java",
)
M336_E15_PREFIXES = (
    "docs/m336_final_freeze_report.md",
    "runs/m336_final_freeze_report.md",
    "runs/m336_final_gate",
)
M336_COMMIT_MESSAGES = (
    "M-33.6 freeze Java acquisition v2",
    "M-33.6 untouched Java black-box evaluation",
    "M-33.6 exact-SHA Java freeze evidence",
)


@dataclass(frozen=True)
class FrozenTreeEntry:
    relative_path: str
    bytes_hash: str


@dataclass(frozen=True)
class FrozenTreeSnapshot:
    phase: str
    commit_sha: str
    entries: tuple[FrozenTreeEntry, ...]
    snapshot_hash: str


@dataclass(frozen=True)
class JavaFreezeProtocolReport:
    f13_snapshot_hash: str
    h13_snapshot_hash: str
    e13_snapshot_hash: str
    f13_to_h13_changed_paths: tuple[str, ...]
    h13_to_e13_changed_paths: tuple[str, ...]
    unauthorized_f13_to_h13_paths: tuple[str, ...]
    unauthorized_h13_to_e13_paths: tuple[str, ...]
    final_input_hashes_absent_from_f13: bool
    production_unchanged_after_f13: bool
    passed: bool
    report_hash: str


@dataclass(frozen=True)
class GitJavaFreezeProtocolReport:
    base_sha: str
    f13_sha: str
    h13_sha: str
    e13_sha: str
    branch_tip_sha: str
    upstream_sha: str
    exact_parent_chain: bool
    exact_commit_messages: bool
    merge_commit_count: int
    excluded_m33_outside_ancestry: bool
    f13_to_h13_changed_paths: tuple[str, ...]
    h13_to_e13_changed_paths: tuple[str, ...]
    unauthorized_f13_to_h13_paths: tuple[str, ...]
    unauthorized_h13_to_e13_paths: tuple[str, ...]
    frozen_paths_changed_after_f13: tuple[str, ...]
    final_hash_overlap_with_f13: tuple[str, ...]
    passed: bool
    report_hash: str


@dataclass(frozen=True)
class M336GitFreezeProtocolReport:
    base_sha: str
    f15_sha: str
    h15_sha: str
    e15_sha: str
    branch_tip_sha: str
    upstream_sha: str
    exact_parent_chain: bool
    exact_commit_messages: bool
    merge_commit_count: int
    excluded_m33_outside_ancestry: bool
    f15_to_h15_changed_paths: tuple[str, ...]
    h15_to_e15_changed_paths: tuple[str, ...]
    unauthorized_f15_to_h15_paths: tuple[str, ...]
    unauthorized_h15_to_e15_paths: tuple[str, ...]
    frozen_paths_changed_after_f15: tuple[str, ...]
    role_manifest_hash: str
    committed_role_manifest_matches: bool
    derived_protected_token_count: int
    protected_disclosure_passed: bool
    passed: bool
    report_hash: str


def frozen_tree_snapshot(phase: str, commit_sha: str, files) -> FrozenTreeSnapshot:
    entries = tuple(
        FrozenTreeEntry(path.replace("\\", "/"), digest)
        for path, digest in sorted(files.items())
    )
    body = {"phase": phase, "commit_sha": commit_sha, "entries": entries}
    return FrozenTreeSnapshot(**body, snapshot_hash=content_hash(body))


def verify_java_freeze_protocol(
    f13: FrozenTreeSnapshot,
    h13: FrozenTreeSnapshot,
    e13: FrozenTreeSnapshot,
    *,
    evaluation_input_prefixes: tuple[str, ...],
    evidence_prefixes: tuple[str, ...],
    production_prefixes: tuple[str, ...] = ("src/", "scripts/", "tools/"),
) -> JavaFreezeProtocolReport:
    """Verify path isolation and hash non-disclosure without creating any refs."""

    for expected, value in (("F13", f13), ("H13", h13), ("E13", e13)):
        _verify_snapshot(value, expected)
    f_map, h_map, e_map = (_entry_map(item) for item in (f13, h13, e13))
    fh = _changed_paths(f_map, h_map)
    he = _changed_paths(h_map, e_map)
    invalid_fh = tuple(
        path for path in fh if not _under(path, evaluation_input_prefixes)
    )
    invalid_he = tuple(path for path in he if not _under(path, evidence_prefixes))
    final_paths = tuple(
        path for path in h_map if _under(path, evaluation_input_prefixes)
    )
    f_hashes = frozenset(f_map.values())
    undisclosed = all(h_map[path] not in f_hashes for path in final_paths)
    production = frozenset(
        path
        for path in set(f_map) | set(h_map) | set(e_map)
        if _under(path, production_prefixes)
    )
    stable = all(
        f_map.get(path) == h_map.get(path) == e_map.get(path) for path in production
    )
    passed = not invalid_fh and not invalid_he and undisclosed and stable
    body = {
        "f13_snapshot_hash": f13.snapshot_hash,
        "h13_snapshot_hash": h13.snapshot_hash,
        "e13_snapshot_hash": e13.snapshot_hash,
        "f13_to_h13_changed_paths": fh,
        "h13_to_e13_changed_paths": he,
        "unauthorized_f13_to_h13_paths": invalid_fh,
        "unauthorized_h13_to_e13_paths": invalid_he,
        "final_input_hashes_absent_from_f13": undisclosed,
        "production_unchanged_after_f13": stable,
        "passed": passed,
    }
    return JavaFreezeProtocolReport(**body, report_hash=content_hash(body))


def _verify_snapshot(value: FrozenTreeSnapshot, expected_phase: str) -> None:
    body = asdict(value)
    claimed = body.pop("snapshot_hash")
    paths = tuple(item.relative_path for item in value.entries)
    if (
        value.phase != expected_phase
        or paths != tuple(sorted(paths))
        or len(paths) != len(set(paths))
        or content_hash(body) != claimed
    ):
        raise ValueError(f"invalid {expected_phase} frozen tree snapshot")


def _entry_map(value):
    return {item.relative_path: item.bytes_hash for item in value.entries}


def _changed_paths(left, right):
    return tuple(
        path
        for path in sorted(set(left) | set(right))
        if left.get(path) != right.get(path)
    )


def _under(path: str, prefixes: tuple[str, ...]) -> bool:
    normalized = _canonical_path(path)
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in (_canonical_path(item.rstrip("/")) for item in prefixes)
    )


def verify_java_git_freeze_protocol(
    repository,
    *,
    base_sha: str,
    f13_sha: str,
    h13_sha: str,
    e13_sha: str,
    excluded_m33_sha: str,
    branch: str,
    h13_prefixes: tuple[str, ...] = M344_H13_PREFIXES,
    e13_prefixes: tuple[str, ...] = M344_E13_PREFIXES,
    frozen_prefixes: tuple[str, ...] = M344_FROZEN_PREFIXES,
    upstream: str | None = None,
) -> GitJavaFreezeProtocolReport:
    """Derive the entire release transition from immutable Git objects."""

    if tuple(sorted(h13_prefixes)) != tuple(sorted(M344_H13_PREFIXES)):
        raise ValueError("incomplete or substituted H13 path policy")
    if tuple(sorted(e13_prefixes)) != tuple(sorted(M344_E13_PREFIXES)):
        raise ValueError("incomplete or substituted E13 path policy")
    if tuple(sorted(frozen_prefixes)) != tuple(sorted(M344_FROZEN_PREFIXES)):
        raise ValueError("incomplete or substituted frozen path policy")

    root = str(repository)
    shas = {
        name: _exact_commit(root, value)
        for name, value in (
            ("base", base_sha),
            ("f13", f13_sha),
            ("h13", h13_sha),
            ("e13", e13_sha),
            ("excluded", excluded_m33_sha),
        )
    }
    parents = {
        name: tuple(_git(root, "rev-list", "--parents", "-n", "1", sha).split()[1:])
        for name, sha in shas.items()
        if name in {"f13", "h13", "e13"}
    }
    exact_chain = (
        parents["f13"] == (shas["base"],)
        and parents["h13"] == (shas["f13"],)
        and parents["e13"] == (shas["h13"],)
    )
    exact_messages = (
        tuple(
            _git(root, "show", "-s", "--format=%s", shas[name])
            for name in ("f13", "h13", "e13")
        )
        == M344_COMMIT_MESSAGES
    )
    merge_count = sum(len(value) != 1 for value in parents.values())
    tip = _exact_commit(root, branch)
    upstream_sha = _exact_commit(root, upstream) if upstream else tip
    outside = not _is_ancestor(root, shas["excluded"], shas["e13"])
    snapshots = {
        name: _git_tree(root, sha, frozen_prefixes)
        for name, sha in shas.items()
        if name in {"f13", "h13", "e13"}
    }
    complete = {
        name: _git_tree(root, sha, ())
        for name, sha in shas.items()
        if name in {"f13", "h13", "e13"}
    }
    fh = _changed_paths(complete["f13"], complete["h13"])
    he = _changed_paths(complete["h13"], complete["e13"])
    invalid_fh = tuple(path for path in fh if not _under(path, h13_prefixes))
    invalid_he = tuple(path for path in he if not _under(path, e13_prefixes))
    frozen_changed = tuple(
        path
        for path in sorted(
            set(snapshots["f13"]) | set(snapshots["h13"]) | set(snapshots["e13"])
        )
        if not (
            snapshots["f13"].get(path)
            == snapshots["h13"].get(path)
            == snapshots["e13"].get(path)
        )
    )
    final_hashes = {
        complete["h13"][path]
        for path in fh
        if path in complete["h13"]
        and _under(path, h13_prefixes)
        and classify_final_artifact_role(path) in PROTECTED_FINAL_ROLES
    }
    overlap = tuple(sorted(final_hashes & set(complete["f13"].values())))
    passed = all(
        (
            exact_chain,
            exact_messages,
            merge_count == 0,
            outside,
            tip == shas["e13"],
            upstream_sha == tip,
            not invalid_fh,
            not invalid_he,
            not frozen_changed,
            not overlap,
        )
    )
    body = {
        "base_sha": shas["base"],
        "f13_sha": shas["f13"],
        "h13_sha": shas["h13"],
        "e13_sha": shas["e13"],
        "branch_tip_sha": tip,
        "upstream_sha": upstream_sha,
        "exact_parent_chain": exact_chain,
        "exact_commit_messages": exact_messages,
        "merge_commit_count": merge_count,
        "excluded_m33_outside_ancestry": outside,
        "f13_to_h13_changed_paths": fh,
        "h13_to_e13_changed_paths": he,
        "unauthorized_f13_to_h13_paths": invalid_fh,
        "unauthorized_h13_to_e13_paths": invalid_he,
        "frozen_paths_changed_after_f13": frozen_changed,
        "final_hash_overlap_with_f13": overlap,
        "passed": passed,
    }
    return GitJavaFreezeProtocolReport(**body, report_hash=content_hash(body))


def verify_m336_git_freeze_protocol(
    repository,
    *,
    f15_sha: str,
    h15_sha: str,
    e15_sha: str,
    upstream: str,
    base_sha: str = M336_BASE_SHA,
    excluded_m33_sha: str = M336_EXCLUDED_M33_SHA,
    branch: str = M336_BRANCH,
    h15_prefixes: tuple[str, ...] = M336_H15_PREFIXES,
    e15_prefixes: tuple[str, ...] = M336_E15_PREFIXES,
    frozen_prefixes: tuple[str, ...] = M336_FROZEN_PREFIXES,
) -> M336GitFreezeProtocolReport:
    """Verify the dedicated E14 -> F15 -> H15 -> E15 release from Git objects."""

    frozen_inputs = (
        (base_sha, M336_BASE_SHA, "base"),
        (excluded_m33_sha, M336_EXCLUDED_M33_SHA, "excluded branch"),
        (branch, M336_BRANCH, "branch"),
        (tuple(sorted(h15_prefixes)), tuple(sorted(M336_H15_PREFIXES)), "H15 paths"),
        (tuple(sorted(e15_prefixes)), tuple(sorted(M336_E15_PREFIXES)), "E15 paths"),
        (
            tuple(sorted(frozen_prefixes)),
            tuple(sorted(M336_FROZEN_PREFIXES)),
            "frozen paths",
        ),
    )
    for actual, expected, label in frozen_inputs:
        if actual != expected:
            raise ValueError(f"incomplete or substituted M-33.6 {label} policy")
    root = str(repository)
    shas = {
        name: _exact_commit(root, value)
        for name, value in (
            ("base", base_sha),
            ("f15", f15_sha),
            ("h15", h15_sha),
            ("e15", e15_sha),
            ("excluded", excluded_m33_sha),
        )
    }
    parents = {
        name: tuple(
            _git(root, "rev-list", "--parents", "-n", "1", shas[name]).split()[1:]
        )
        for name in ("f15", "h15", "e15")
    }
    exact_chain = (
        parents["f15"] == (shas["base"],)
        and parents["h15"] == (shas["f15"],)
        and parents["e15"] == (shas["h15"],)
    )
    exact_messages = (
        tuple(
            _git(root, "show", "-s", "--format=%s", shas[name])
            for name in ("f15", "h15", "e15")
        )
        == M336_COMMIT_MESSAGES
    )
    merge_count = sum(len(value) != 1 for value in parents.values())
    tip = _exact_commit(root, branch)
    upstream_sha = _exact_commit(root, upstream)
    outside = not _is_ancestor(root, shas["excluded"], shas["e15"])
    complete = {name: _git_tree(root, shas[name], ()) for name in ("f15", "h15", "e15")}
    frozen = {
        name: _git_tree(root, shas[name], frozen_prefixes)
        for name in ("f15", "h15", "e15")
    }
    fh = _changed_paths(complete["f15"], complete["h15"])
    he = _changed_paths(complete["h15"], complete["e15"])
    invalid_fh = tuple(path for path in fh if not _under(path, h15_prefixes))
    invalid_he = tuple(path for path in he if not _under(path, e15_prefixes))
    frozen_changed = tuple(
        path
        for path in sorted(set().union(*(set(value) for value in frozen.values())))
        if not (
            frozen["f15"].get(path)
            == frozen["h15"].get(path)
            == frozen["e15"].get(path)
        )
    )
    f_bytes = _git_blob_bytes(root, shas["f15"], tuple(complete["f15"]))
    h_paths = tuple(path for path in fh if path in complete["h15"])
    h_bytes = _git_blob_bytes(root, shas["h15"], h_paths)
    role_manifest = build_final_artifact_role_manifest(h_bytes)
    committed_role_path = "evaluation/m336_final_java/role_manifest.json"
    committed_role_manifest_matches = committed_role_path in h_bytes and json.loads(
        h_bytes[committed_role_path].decode("utf-8")
    ) == asdict(role_manifest)
    disclosure = verify_role_aware_disclosure(f_bytes, h_bytes, role_manifest)
    passed = all(
        (
            exact_chain,
            exact_messages,
            merge_count == 0,
            outside,
            tip == shas["e15"],
            upstream_sha == tip,
            not invalid_fh,
            not invalid_he,
            not frozen_changed,
            committed_role_manifest_matches,
            disclosure.passed,
        )
    )
    body = {
        "base_sha": shas["base"],
        "f15_sha": shas["f15"],
        "h15_sha": shas["h15"],
        "e15_sha": shas["e15"],
        "branch_tip_sha": tip,
        "upstream_sha": upstream_sha,
        "exact_parent_chain": exact_chain,
        "exact_commit_messages": exact_messages,
        "merge_commit_count": merge_count,
        "excluded_m33_outside_ancestry": outside,
        "f15_to_h15_changed_paths": fh,
        "h15_to_e15_changed_paths": he,
        "unauthorized_f15_to_h15_paths": invalid_fh,
        "unauthorized_h15_to_e15_paths": invalid_he,
        "frozen_paths_changed_after_f15": frozen_changed,
        "role_manifest_hash": role_manifest.manifest_hash,
        "committed_role_manifest_matches": committed_role_manifest_matches,
        "derived_protected_token_count": disclosure.derived_protected_token_count,
        "protected_disclosure_passed": disclosure.passed,
        "passed": passed,
    }
    return M336GitFreezeProtocolReport(**body, report_hash=content_hash(body))


def _git_blob_bytes(repository: str, commit_sha: str, paths) -> dict[str, bytes]:
    result = {}
    for path in paths:
        process = subprocess.run(
            ["git", "-C", repository, "show", f"{commit_sha}:{path}"],
            check=True,
            capture_output=True,
        )
        result[path] = process.stdout
    return result


def _git_tree(repository: str, commit_sha: str, frozen_prefixes):
    raw = subprocess.run(
        ["git", "-C", repository, "ls-tree", "-r", "-z", commit_sha],
        check=True,
        capture_output=True,
    ).stdout
    result = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, encoded_path = entry.split(b"\t", 1)
        mode, kind, object_sha = metadata.decode("ascii").split()
        path = _canonical_path(encoded_path.decode("utf-8"))
        if kind != "blob":
            continue
        if mode == "120000" and (not frozen_prefixes or _under(path, frozen_prefixes)):
            raise ValueError("symlink is forbidden in Java freeze scope")
        if path in result:
            raise ValueError("duplicate normalized Git tree path")
        if not frozen_prefixes or _under(path, frozen_prefixes):
            result[path] = object_sha
    return result


def _canonical_path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError("non-canonical Git path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe Git path")
    return path.as_posix()


def _exact_commit(repository: str, value: str) -> str:
    sha = _git(repository, "rev-parse", "--verify", f"{value}^{{commit}}")
    _git(repository, "cat-file", "-e", f"{sha}^{{commit}}")
    return sha


def _is_ancestor(repository: str, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", repository, "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
        capture_output=True,
    )
    if result.returncode not in {0, 1}:
        raise ValueError("Git ancestry query failed")
    return result.returncode == 0


def _git(repository: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repository, *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
