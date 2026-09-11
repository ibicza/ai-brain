"""Validate or execute the canonical M-33.6k.4 typed final route."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2HermeticCommandWorker,
    build_m336k2_native_execution_plan,
    executable_dependency_manifest_from_dict,
    execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    M336K2RouteLedger,
)
from ai_brain.stage3.acquisition.m336k4_controller import (
    M336K4IdentityCheckingWorker,
    run_m336k4_final_controller,
    verify_m336k4_route_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k4_request import (
    build_m336k4_internal_stage_request,
    validate_m336k4_final_invocation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--validation-receipt", type=Path)
    args = parser.parse_args()
    request_path = args.request.resolve(strict=True)
    validated = validate_m336k4_final_invocation(request_path)
    if args.validation_receipt is not None:
        output = args.validation_receipt.resolve(strict=False)
        if output.exists():
            raise FileExistsError("M336K4 validation receipt output must be fresh")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            canonical_json(asdict(validated.receipt)) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.validate_only:
        print(canonical_json(asdict(validated.receipt)))
        return
    if validated.request.purpose == "QUALIFICATION":
        raise M336K2ProtocolError("M336K4 qualification request is not executable")
    # This is the mandatory immediate-before-controller validation.  Nothing in
    # between can spend a ledger, reserve a one-shot, create a vault, or issue a
    # source request.
    second = validate_m336k4_final_invocation(request_path)
    if second.receipt != validated.receipt:
        raise RuntimeError("M336K4 repeated exact invocation validation changed")
    request = validated.request
    internal_request = build_m336k4_internal_stage_request(validated)
    private_root = Path(request.private_root).resolve(strict=False)
    private_root.mkdir(parents=True)
    stage_request_path = private_root / "canonical-internal-stage-request.json"
    stage_request_path.write_text(
        canonical_json(internal_request) + "\n", encoding="utf-8", newline="\n"
    )
    components = {item.name: item for item in validated.freeze.components}
    dependency = executable_dependency_manifest_from_dict(
        _component_object(
            Path(request.repository), components, "executable_dependency_manifest"
        )
    )
    capsule = execution_capsule_receipt_from_dict(
        _component_object(
            Path(request.repository), components, "execution_capsule_receipt"
        )
    )
    plan = build_m336k2_native_execution_plan(
        repository=Path(request.repository),
        python_executable=Path(request.python_executable),
        stage_request=stage_request_path,
        stage_receipt_root=Path(request.stage_receipt_root),
        route_run_id=validated.bundle.protocol_run_id.value,
        exact_f28_sha=request.exact_f29_sha,
        route_registry_hash=capsule.route_registry_hash,
        dependency_manifest=dependency,
        capsule=capsule,
    )
    ledger = M336K2RouteLedger(
        Path(request.route_ledger),
        git_worktrees=_worktrees(
            Path(request.repository), Path(request.git_executable)
        ),
    )
    worker = M336K4IdentityCheckingWorker(
        M336K2HermeticCommandWorker(plan),
        receipt_root=Path(request.stage_receipt_root),
        bundle=validated.bundle,
    )
    result = run_m336k4_final_controller(
        validated=validated,
        ledger=ledger,
        preledger_guard=lambda: validated.receipt,
        worker=worker,
        output=Path(request.route_receipt),
    )
    verify_m336k4_route_ledger_identity(
        ledger,
        bundle=validated.bundle,
        exact_f29_sha=request.exact_f29_sha,
        preledger_receipt_hash=validated.receipt.receipt_hash,
    )
    print(canonical_json(asdict(result)))


def _component_object(root: Path, components: dict, name: str) -> dict:
    component = components[name]
    path = root.joinpath(*Path(component.relative_path).parts).resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"M336K4 frozen component is not an object: {name}")
    return value


def _worktrees(repository: Path, git: Path) -> tuple[Path, ...]:
    import subprocess

    raw = subprocess.run(
        (str(git.resolve(strict=True)), "worktree", "list", "--porcelain", "-z"),
        cwd=repository.resolve(strict=True),
        check=True,
        capture_output=True,
    ).stdout
    return tuple(
        Path(item.removeprefix(b"worktree ").decode("utf-8")).resolve(strict=True)
        for item in raw.split(b"\0")
        if item.startswith(b"worktree ")
    )


if __name__ == "__main__":
    main()
