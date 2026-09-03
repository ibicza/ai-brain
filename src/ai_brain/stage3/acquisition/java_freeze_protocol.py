"""Static verifier for the future F13 -> H13 -> E13 Java freeze protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash


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
        f_map.get(path) == h_map.get(path) == e_map.get(path)
        for path in production
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
    return any(path == item.rstrip("/") or path.startswith(item) for item in prefixes)
