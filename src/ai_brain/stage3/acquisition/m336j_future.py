"""Pre-freeze registry for every future M-33.6j F25/H25/E25 entrypoint."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash


@dataclass(frozen=True)
class M336JFutureEntrypoint:
    phase: str
    python_module: str
    qualified_callable_name: str
    source_file_hash: str
    callable_signature_hash: str
    entrypoint_hash: str


@dataclass(frozen=True)
class M336JFutureOrchestrationManifest:
    schema_version: int
    contract_role: str
    entrypoints: tuple[M336JFutureEntrypoint, ...]
    entrypoint_count: int
    unresolved_entrypoint_count: int
    post_q25_implementation_file_count: int
    status: str
    manifest_hash: str


_FUTURE_ENTRYPOINTS = (
    (
        "F25_FREEZE_CONSTRUCTION",
        "scripts.m336j_build_f25",
        "main",
    ),
    (
        "FINAL_AUTHORIZATION_CONSTRUCTION",
        "ai_brain.stage3.acquisition.m336j_freeze",
        "build_m336j_final_acquisition_authorization",
    ),
    (
        "FINAL_CONTROLLER",
        "scripts.m336i_java_final_route",
        "_final",
    ),
    (
        "H25_PUBLIC_PRODUCTION_STAGING",
        "scripts.m336i_publish_h24",
        "main",
    ),
    (
        "E25_EVIDENCE_STAGING",
        "scripts.m336i_publish_e24",
        "main",
    ),
    (
        "COMMIT_AND_PATH_VERIFICATION",
        "ai_brain.stage3.acquisition.m336j_future",
        "verify_m336j_commit_transition",
    ),
    (
        "EXACT_QUALITY",
        "scripts.m336j_run_exact_quality",
        "main",
    ),
    (
        "FINAL_OUTCOME_DERIVATION",
        "scripts.m336i_java_final_route",
        "_stage_public",
    ),
)


def build_m336j_future_orchestration_manifest() -> M336JFutureOrchestrationManifest:
    entries = tuple(_entrypoint(*spec) for spec in _FUTURE_ENTRYPOINTS)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_FUTURE_ORCHESTRATION_MANIFEST",
        "entrypoints": entries,
        "entrypoint_count": len(entries),
        "unresolved_entrypoint_count": 0,
        "post_q25_implementation_file_count": 0,
        "status": "PASS",
    }
    result = M336JFutureOrchestrationManifest(**body, manifest_hash=content_hash(body))
    verify_m336j_future_orchestration_manifest(result)
    return result


def verify_m336j_future_orchestration_manifest(
    manifest: M336JFutureOrchestrationManifest,
) -> None:
    rebuilt = build_m336j_future_orchestration_manifest_without_verification()
    if manifest != rebuilt:
        raise ValueError("M336J future orchestration manifest changed")


def build_m336j_future_orchestration_manifest_without_verification() -> (
    M336JFutureOrchestrationManifest
):
    entries = tuple(_entrypoint(*spec) for spec in _FUTURE_ENTRYPOINTS)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_FUTURE_ORCHESTRATION_MANIFEST",
        "entrypoints": entries,
        "entrypoint_count": len(entries),
        "unresolved_entrypoint_count": 0,
        "post_q25_implementation_file_count": 0,
        "status": "PASS",
    }
    return M336JFutureOrchestrationManifest(**body, manifest_hash=content_hash(body))


def verify_m336j_commit_transition(
    repository: Path,
    *,
    parent_sha: str,
    commit_sha: str,
    expected_message: str,
    allowed_prefixes: tuple[str, ...],
) -> dict:
    """Verify an exact clean linear commit and its bounded changed paths."""

    root = repository.resolve(strict=True)
    head = _git(root, "rev-parse", "HEAD^{commit}")
    parent = _git(root, "rev-parse", f"{commit_sha}^1")
    message = _git(root, "show", "-s", "--format=%s", commit_sha)
    status = _git(root, "status", "--porcelain=v1")
    merge_count = int(
        _git(root, "rev-list", "--count", "--merges", f"{parent_sha}..{commit_sha}")
    )
    changed = tuple(
        line
        for line in _git(
            root, "diff", "--name-only", f"{parent_sha}..{commit_sha}"
        ).splitlines()
        if line
    )
    forbidden = tuple(path for path in changed if not path.startswith(allowed_prefixes))
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_COMMIT_TRANSITION_RECEIPT",
        "parent_sha": parent_sha,
        "commit_sha": commit_sha,
        "head_matches": head == commit_sha,
        "parent_matches": parent == parent_sha,
        "message_matches": message == expected_message,
        "worktree_clean": not status,
        "merge_commit_count": merge_count,
        "changed_path_count": len(changed),
        "forbidden_changed_path_count": len(forbidden),
        "status": "PASS",
    }
    if not all(
        (
            body["head_matches"],
            body["parent_matches"],
            body["message_matches"],
            body["worktree_clean"],
            not merge_count,
            not forbidden,
        )
    ):
        raise ValueError("M336J commit transition is invalid")
    return {**body, "receipt_hash": content_hash(body)}


def _entrypoint(
    phase: str, module_name: str, callable_name: str
) -> M336JFutureEntrypoint:
    module = _import_entrypoint_module(module_name)
    value = module
    for part in callable_name.split("."):
        value = getattr(value, part)
    source = inspect.getsourcefile(value)
    if not callable(value) or source is None:
        raise ValueError("M336J future entrypoint is unresolved")
    body = {
        "phase": phase,
        "python_module": module_name,
        "qualified_callable_name": callable_name,
        "source_file_hash": bytes_hash(Path(source).resolve(strict=True).read_bytes()),
        "callable_signature_hash": content_hash(str(inspect.signature(value))),
    }
    return M336JFutureEntrypoint(**body, entrypoint_hash=content_hash(body))


def _import_entrypoint_module(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if not module_name.startswith("scripts.") or error.name != "scripts":
            raise
    repository = Path(__file__).resolve().parents[4]
    source = repository.joinpath(*module_name.split(".")).with_suffix(".py")
    if not source.is_file():
        raise ValueError("M336J script entrypoint source is unavailable")
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ValueError("M336J script entrypoint cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
