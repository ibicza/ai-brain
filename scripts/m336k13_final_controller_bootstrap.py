"""Controller-only bootstrap that attests the exact loaded M336K13 plan."""

from __future__ import annotations

import argparse
import hashlib
import os
import runpy
import sys
from pathlib import Path

from m336k5_python_bootstrap import (
    _content_hash,
    _normalized,
    _strict_object,
    _verify_and_receipt,
    _write_receipt,
)


def _load_plan(args: argparse.Namespace) -> tuple[dict, bytes]:
    if (args.invocation_plan is None) == (args.inline_plan_json is None):
        raise RuntimeError("M336K13 bootstrap requires one invocation plan source")
    if args.invocation_plan is not None:
        raw = Path(args.invocation_plan).resolve(strict=True).read_bytes()
    else:
        raw = args.inline_plan_json.encode("utf-8")
    value = _strict_object(raw)
    body = dict(value)
    claimed = body.pop("invocation_plan_hash", None)
    if not isinstance(claimed, str) or _content_hash(body) != claimed:
        raise RuntimeError("M336K13 invocation plan hash changed")
    return value, raw


def _path_identity(path: str | Path) -> str:
    return _content_hash(
        {
            "identity_kind": "NORMALIZED_ABSOLUTE_PRIVATE_PATH",
            "normalized_path": _normalized(path),
        }
    )


def _actual_launcher_receipt(
    *,
    plan: dict,
    raw_plan: bytes,
    plan_path: Path,
    operation: str,
    startup_receipt: dict,
    execution_scope: str,
) -> dict:
    selected_arguments = plan[f"{operation}_arguments"]
    policy = plan["startup_policy"]
    environment = plan["sanitized_environment"]
    body = {
        "schema_version": 1,
        "contract_role": "M336K13_ACTUAL_LAUNCHER_PLAN_RECEIPT",
        "execution_scope": execution_scope,
        "actual_invocation_plan_hash": plan["invocation_plan_hash"],
        "actual_plan_bytes_hash": hashlib.sha256(raw_plan).hexdigest(),
        "actual_plan_file_identity_hash": _path_identity(plan_path),
        "selected_operation": operation,
        "selected_target_kind": plan["target_kind"],
        "selected_target_source_hash": plan["expected_target_source_hash"],
        "selected_operation_argument_hash": _content_hash(selected_arguments),
        "startup_receipt_hash": startup_receipt["receipt_hash"],
        "startup_policy_hash": policy["policy_hash"],
        "sanitized_environment_hash": environment["environment_hash"],
        "project_source_identity_hash": plan["expected_project_source_identity"],
        "interpreter_binding_hash": startup_receipt["interpreter_binding_hash"],
        "outer_invocation_argument_hash": _content_hash(
            [
                "-s",
                "-B",
                _normalized(plan["bootstrap_script"]),
                "--invocation-plan",
                _normalized(plan_path),
                "--operation",
                operation,
            ]
        ),
        "forbidden_variable_occurrence_count": sum(
            name in os.environ for name in policy["forbidden_environment_names"]
        ),
        "unexpected_variable_count": len(
            set(os.environ) - {item[0] for item in environment["variables"]}
        ),
        "attestation_before_target_dispatch": True,
        "status": "PASS",
    }
    return {**body, "receipt_hash": _content_hash(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--invocation-plan")
    source.add_argument("--inline-plan-json")
    parser.add_argument("--operation", choices=("validate", "execute"), required=True)
    parser.add_argument("--actual-launcher-plan-receipt", required=True)
    parser.add_argument(
        "--execution-scope",
        choices=("OFFICIAL_CONTROLLER", "REHEARSAL"),
        required=True,
    )
    args = parser.parse_args()
    if args.invocation_plan is None:
        raise RuntimeError("M336K13 actual attestation requires a plan file")
    plan, raw_plan = _load_plan(args)
    receipt = _verify_and_receipt(plan)
    receipt_path = Path(plan[f"{args.operation}_startup_receipt"])
    _write_receipt(receipt_path, receipt)
    actual_path = Path(args.actual_launcher_plan_receipt)
    bound_paths = {
        _normalized(args.invocation_plan),
        _normalized(plan["validate_arguments"][1]),
        _normalized(plan["validate_arguments"][4]),
        _normalized(plan["execute_arguments"][5]),
        _normalized(plan["validate_startup_receipt"]),
        _normalized(plan["execute_startup_receipt"]),
    }
    if not actual_path.is_absolute() or _normalized(actual_path) in bound_paths:
        raise RuntimeError(
            "M336K13 actual launcher receipt destination collides with a plan role"
        )
    actual = _actual_launcher_receipt(
        plan=plan,
        raw_plan=raw_plan,
        plan_path=Path(args.invocation_plan).resolve(strict=True),
        operation=args.operation,
        startup_receipt=receipt,
        execution_scope=args.execution_scope,
    )
    _write_receipt(actual_path, actual)
    repository = Path(plan["repository"]).resolve(strict=True)
    sys.path[:0] = [str(repository / "src"), str(repository)]
    arguments = list(plan[f"{args.operation}_arguments"])
    arguments.extend(("--startup-receipt", str(receipt_path)))
    arguments.extend(
        (
            "--actual-launcher-plan-receipt",
            str(actual_path.resolve(strict=True)),
        )
    )
    sys.argv = [str(plan["target"]), *arguments]
    if plan["target_kind"] == "SCRIPT":
        runpy.run_path(
            str(Path(plan["target"]).resolve(strict=True)), run_name="__main__"
        )
    elif plan["target_kind"] == "MODULE":
        runpy.run_module(str(plan["target"]), run_name="__main__", alter_sys=True)
    else:
        raise RuntimeError("M336K13 bootstrap target kind changed")


if __name__ == "__main__":
    main()
