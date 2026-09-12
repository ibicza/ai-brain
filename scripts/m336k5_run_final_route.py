"""Validate or execute the canonical M-33.6k.5 typed final route."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_execution import (
    build_m336k2_native_execution_plan,
    executable_dependency_manifest_from_dict,
    execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    M336K2RouteLedger,
)
from ai_brain.stage3.acquisition.m336k5_controller import (
    M336K5IdentityCheckingWorker,
    run_m336k5_final_controller,
    verify_m336k5_route_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k5_execution import (
    M336K5HermeticCommandWorker,
)
from ai_brain.stage3.acquisition.m336k5_request import (
    build_m336k5_internal_stage_request,
    validate_m336k5_final_invocation,
)
from ai_brain.stage3.acquisition.m336k5_resources import M336K5ResourceMonitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--validation-receipt", type=Path)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    request_path = args.request.resolve(strict=True)
    startup_receipt_path = args.startup_receipt.resolve(strict=True)
    validated = validate_m336k5_final_invocation(
        request_path, startup_receipt_path=startup_receipt_path
    )
    if args.validation_receipt is not None:
        output = args.validation_receipt.resolve(strict=False)
        if output.exists():
            raise FileExistsError("M336K5 validation receipt output must be fresh")
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
        raise M336K2ProtocolError("M336K5 qualification request is not executable")
    # This is the mandatory immediate-before-controller validation.  Nothing in
    # between can spend a ledger, reserve a one-shot, create a vault, or issue a
    # source request.
    second = validate_m336k5_final_invocation(
        request_path, startup_receipt_path=startup_receipt_path
    )
    if second.receipt != validated.receipt:
        raise RuntimeError("M336K5 repeated exact invocation validation changed")
    request = validated.request
    internal_request = build_m336k5_internal_stage_request(validated)
    private_root = Path(request.private_root).resolve(strict=False)
    private_root.mkdir(parents=True)
    monitor = M336K5ResourceMonitor(
        ledger=private_root / "m336k5-resource-samples.jsonl",
        filesystem_root=private_root,
        private_root=private_root,
        temp_root=Path(request.stage_receipt_root),
    )
    monitor.start("OFFICIAL_ROUTE")
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
        exact_f28_sha=request.exact_f30_sha,
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
    worker = M336K5IdentityCheckingWorker(
        M336K5HermeticCommandWorker(
            plan,
            repository=Path(request.repository),
            git_executable=Path(request.git_executable),
            python_executable=Path(request.python_executable),
            powershell_executable=Path(request.executable_handles["powershell"]),
            bootstrap_script=(
                Path(request.repository) / "scripts" / "m336k5_python_bootstrap.py"
            ),
            expected_startup_receipt_hash=validated.receipt.startup_receipt_hash,
            resource_monitor=monitor,
        ),
        receipt_root=Path(request.stage_receipt_root),
        bundle=validated.bundle,
        expected_startup_receipt_hash=validated.receipt.startup_receipt_hash,
    )
    try:
        result = run_m336k5_final_controller(
            validated=validated,
            ledger=ledger,
            preledger_guard=lambda: validated.receipt,
            worker=worker,
            output=Path(request.route_receipt),
        )
    finally:
        monitor.stop("OFFICIAL_ROUTE")
    verify_m336k5_route_ledger_identity(
        ledger,
        bundle=validated.bundle,
        exact_f30_sha=request.exact_f30_sha,
        preledger_receipt_hash=validated.receipt.receipt_hash,
    )
    print(canonical_json(asdict(result)))


def _component_object(root: Path, components: dict, name: str) -> dict:
    component = components[name]
    path = root.joinpath(*Path(component.relative_path).parts).resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"M336K5 frozen component is not an object: {name}")
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
