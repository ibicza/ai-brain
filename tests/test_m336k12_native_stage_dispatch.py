from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_controller import M336K2StageRequest
from ai_brain.stage3.acquisition.m336k2_execution import M336K2_COMMAND_EVENTS
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_execution import M336K5HermeticCommandWorker
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_startup_policy,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k11_execution import (
    M336K11NativeExecutionCapsuleReceipt,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12_COMPATIBILITY_MARKER,
    M336K12_MUTATION_CASES,
    M336K12_STAGE_WORKER,
    M336K12DisposableDispatchClosure,
    M336K12NativeExecutionCapsuleReceipt,
    M336K12NativeStagePlanBinding,
    M336K12PreledgerDispatchAdmissionPolicy,
    build_m336k12_native_execution_plan,
    build_m336k12_native_stage_dispatches,
    verify_m336k12_native_stage_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def _closure(
    tmp_path: Path,
    *,
    execution_scope: str = "REHEARSAL",
    profile_hash: str = "c" * 64,
):
    dispatches = build_m336k12_native_stage_dispatches(
        repository=ROOT,
        execution_scope=execution_scope,
        bootstrap_script=ROOT / "scripts/m336k5_python_bootstrap.py",
    )
    plan = build_m336k12_native_execution_plan(
        repository=ROOT,
        python_executable=Path(sys.executable),
        stage_request=tmp_path / "private-request.json",
        stage_receipt_root=tmp_path / "receipts",
        route_run_id="m336k8.disposable.native-stage-dispatch.v5",
        exact_f37_sha="a" * 40,
        route_registry_hash="b" * 64,
        dispatches=dispatches,
    )
    binding = M336K12NativeStagePlanBinding.build(
        repository=ROOT,
        exact_implementation_tip="a" * 40,
        active_profile_hash=profile_hash,
        route_registry_hash="b" * 64,
        typed_route_manifest_hash="d" * 64,
        dispatches=dispatches,
        python_executable=Path(sys.executable),
        outer_startup_policy_hash=build_m336k5_python_startup_policy().policy_hash,
        native_capsule_receipt_hash="e" * 64,
    )
    return dispatches, plan, binding


def _active_capsule(tmp_path: Path):
    dispatches, plan, binding = _closure(
        tmp_path, execution_scope="OFFICIAL_CONTROLLER"
    )
    parity = verify_m336k12_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=binding,
        repository=ROOT,
    )
    base = M336K11NativeExecutionCapsuleReceipt.from_dict(
        json.loads(
            (
                ROOT
                / "artifacts/m336k11/f36-freeze/components/29-execution_capsule_receipt.json"
            ).read_text(encoding="utf-8")
        )
    )
    return (
        M336K12NativeExecutionCapsuleReceipt.build(
            base_capsule=base,
            plan_binding=binding,
            parity=parity,
            dispatches=dispatches,
        ),
        base,
    )


def _rehash_command(command, arguments):
    body = {
        "schema_version": command.schema_version,
        "event": command.event,
        "executable": command.executable,
        "arguments": arguments,
        "working_directory": command.working_directory,
        "receipt_path": command.receipt_path,
        "receipt_hash_field": command.receipt_hash_field,
        "expected_status": command.expected_status,
    }
    return replace(command, arguments=arguments, specification_hash=content_hash(body))


def _rehash_plan(plan, commands):
    body = {
        "schema_version": plan.schema_version,
        "route_run_id": plan.route_run_id,
        "exact_f28_sha": plan.exact_f28_sha,
        "route_registry_hash": plan.route_registry_hash,
        "commands": commands,
    }
    return replace(plan, commands=commands, plan_hash=content_hash(body))


def _rehash_dataclass(value, hash_field: str, **changes):
    changed = replace(value, **changes, **{hash_field: "0" * 64})
    body = asdict(changed)
    body.pop(hash_field)
    return replace(changed, **{hash_field: content_hash(body)})


def test_m336k12_complete_plan_has_one_typed_producer_and_consumer(
    tmp_path: Path,
) -> None:
    dispatches, plan, binding = _closure(tmp_path)
    receipt = verify_m336k12_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=binding,
        repository=ROOT,
    )

    assert tuple(item.event for item in dispatches) == M336K2_COMMAND_EVENTS
    assert all(
        command.arguments[0] == M336K12_COMPATIBILITY_MARKER
        for command in plan.commands
    )
    assert all(
        Path(command.arguments[1]) == ROOT / M336K12_STAGE_WORKER
        for command in plan.commands
    )
    assert all("-s" not in command.arguments[2:] for command in plan.commands)
    assert all("-B" not in command.arguments[2:] for command in plan.commands)
    assert receipt.status == "PASS"
    assert receipt.produced_dispatch_count == len(M336K2_COMMAND_EVENTS)
    assert receipt.accepted_dispatch_count == len(M336K2_COMMAND_EVENTS)
    M336K12PreledgerDispatchAdmissionPolicy.build(ROOT).verify()


def test_m336k12_disposable_closure_uses_active_builder_and_consumer(
    tmp_path: Path,
) -> None:
    profile = m336k_official_profile_registry().profile("m336k8-rehearsal-v2")
    dispatches, plan, binding = _closure(tmp_path, profile_hash=profile.profile_hash)
    parity = verify_m336k12_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=binding,
        repository=ROOT,
    )
    closure = M336K12DisposableDispatchClosure.build(
        rehearsal_profile_id=profile.profile_id,
        dispatches=dispatches,
        plan_binding=binding,
        parity=parity,
    )

    decoded = M336K12DisposableDispatchClosure.from_dict(
        json.loads(json.dumps(closure.canonical_object()))
    )

    assert decoded == closure
    assert closure.plan_builder_source_difference_count == 0
    assert closure.consumer_source_difference_count == 0
    assert closure.producer_consumer_parity.status == "PASS"


@pytest.mark.parametrize(
    "prefix",
    [
        ("-s", "-B"),
        ("-s",),
        (),
        ("-B", "-B"),
    ],
)
def test_m336k12_rejects_fully_rehashed_unversioned_offsets(
    tmp_path: Path, prefix: tuple[str, ...]
) -> None:
    dispatches, plan, binding = _closure(tmp_path)
    original = plan.commands[0]
    mutated_arguments = prefix + original.arguments[1:]
    mutated = _rehash_command(original, mutated_arguments)
    mutated_plan = _rehash_plan(plan, (mutated, *plan.commands[1:]))

    with pytest.raises(M336K2ProtocolError):
        verify_m336k12_native_stage_plan(
            plan=mutated_plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )


def test_m336k12_rejects_duplicate_receipt_destination(tmp_path: Path) -> None:
    dispatches, plan, binding = _closure(tmp_path)
    first = plan.commands[0]
    second = plan.commands[1]
    arguments = (*second.arguments[:-1], first.receipt_path)
    duplicated = replace(
        _rehash_command(second, arguments), receipt_path=first.receipt_path
    )
    duplicated = _rehash_command(duplicated, arguments)
    mutated_plan = _rehash_plan(plan, (first, duplicated, *plan.commands[2:]))

    with pytest.raises(M336K2ProtocolError):
        verify_m336k12_native_stage_plan(
            plan=mutated_plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )


@pytest.mark.parametrize("case", M336K12_MUTATION_CASES)
def test_m336k12_closed_under_rehash_mutations(case: str, tmp_path: Path) -> None:
    dispatches, plan, binding = _closure(tmp_path)
    number = M336K12_MUTATION_CASES.index(case) + 1
    first = plan.commands[0]
    arguments = first.arguments
    operation = None

    if number in {1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 29, 40}:
        changed = {
            1: ("-s", "-B", *arguments[1:]),
            2: ("-s", *arguments[1:]),
            3: arguments[1:],
            4: ("-B", "-B", *arguments[1:]),
            5: (arguments[1], "-B", *arguments[2:]),
            6: ("-B", "offset-padding", *arguments[1:]),
            7: (
                "-B",
                str(ROOT / "scripts/m336k5_python_bootstrap.py"),
                *arguments[2:],
            ),
            9: (*arguments[:2], *arguments[3:]),
            10: (*arguments[:3], arguments[4], arguments[3], *arguments[5:]),
            11: (*arguments[:4], *arguments[5:]),
            12: (*arguments[:5], plan.commands[1].event, *arguments[6:]),
            13: (*arguments[:6], *arguments[7:]),
            14: (*arguments[:7], arguments[3]),
            29: ("-s", "-B", *arguments[1:]),
            40: (*arguments, "--private-environment", "RAW_PRIVATE_VALUE"),
        }[number]
        mutated = _rehash_command(first, tuple(changed))
        mutated_plan = _rehash_plan(plan, (mutated, *plan.commands[1:]))
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=mutated_plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )
    elif number == 8:
        changed = _rehash_dataclass(
            dispatches[0], "dispatch_hash", target_source_hash=content_hash(case)
        )
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=(changed, *dispatches[1:]),
            plan_binding=binding,
            repository=ROOT,
        )
    elif number == 15:
        second = plan.commands[1]
        duplicate_arguments = (*second.arguments[:-1], first.receipt_path)
        duplicate = replace(
            _rehash_command(second, duplicate_arguments),
            receipt_path=first.receipt_path,
        )
        duplicate = _rehash_command(duplicate, duplicate_arguments)
        mutated_plan = _rehash_plan(plan, (first, duplicate, *plan.commands[2:]))
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=mutated_plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )
    elif number in {16, 17, 18}:
        commands = {
            16: (plan.commands[1], plan.commands[0], *plan.commands[2:]),
            17: plan.commands[:-1],
            18: (*plan.commands, plan.commands[-1]),
        }[number]
        mutated_plan = _rehash_plan(plan, tuple(commands))
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=mutated_plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )
    elif number == 19:
        mutated = replace(
            first,
            executable=str(ROOT / "scripts/m336k5_python_bootstrap.py"),
            specification_hash="0" * 64,
        )
        body = asdict(mutated)
        body.pop("specification_hash")
        mutated = replace(mutated, specification_hash=content_hash(body))
        mutated_plan = _rehash_plan(plan, (mutated, *plan.commands[1:]))
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=mutated_plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )
    elif number == 39:
        parity = verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )
        worker = M336K5HermeticCommandWorker(
            plan,
            repository=ROOT,
            git_executable=Path(sys.executable),
            python_executable=Path(sys.executable),
            powershell_executable=Path(sys.executable),
            bootstrap_script=ROOT / "scripts/m336k5_python_bootstrap.py",
            expected_startup_receipt_hash="f" * 64,
            native_stage_dispatches=dispatches,
            native_stage_plan_binding=binding,
            producer_consumer_parity=parity,
        )
        foreign_startup = tmp_path / "receipts" / "ACQUISITION_RESERVED.startup.json"
        foreign_startup.parent.mkdir(parents=True)
        foreign_startup.write_text("{}\n", encoding="utf-8", newline="\n")
        request_body = {
            "schema_version": 1,
            "event": "ACQUISITION_RESERVED",
            "route_run_id": plan.route_run_id,
            "execution_mode": "REHEARSAL",
            "exact_f28_sha": plan.exact_f28_sha,
            "context_hash": "1" * 64,
            "previous_operation_hash": "2" * 64,
        }
        stage_request = M336K2StageRequest(
            **request_body, request_hash=content_hash(request_body)
        )
        operation = lambda: worker(stage_request)
    elif number in {20, 21, 22, 23}:
        changed = _rehash_dataclass(
            dispatches[0],
            "dispatch_hash",
            outer_interpreter_argument_hash=content_hash(case),
        )
        operation = changed.verify
    elif number == 24:
        changed = _rehash_dataclass(
            dispatches[0], "dispatch_hash", bootstrap_source_hash=content_hash(case)
        )
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=(changed, *dispatches[1:]),
            plan_binding=binding,
            repository=ROOT,
        )
    elif number in {25, 26, 27, 30}:
        field = {
            25: "bootstrap_repository_path",
            26: "plan_builder_source_hash",
            27: "consumer_source_hash",
            30: "consumer_source_hash",
        }[number]
        changed_binding = _rehash_dataclass(
            binding,
            "plan_binding_hash",
            **{field: (M336K12_STAGE_WORKER if number == 25 else content_hash(case))},
        )
        operation = lambda: verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=changed_binding,
            repository=ROOT,
        )
    elif number in {33, 34, 35, 36, 37, 38}:
        admission = M336K12PreledgerDispatchAdmissionPolicy.build(ROOT)
        changes = {
            33: {"validate_only_complete_plan_preflight_required": False},
            34: {"controller_complete_plan_preflight_required": False},
            35: {"first_stage_handoff_mode": "IN_PROCESS_PARSER_CALL"},
            36: {"rehearsal_plan_builder_source_hash": content_hash(case)},
            37: {"route_event_count_before_plan_admission": 1},
            38: {"subprocess_start_count_before_plan_admission": 1},
        }[number]
        changed = _rehash_dataclass(admission, "policy_hash", **changes)
        operation = changed.verify
    elif number == 28:
        changed = _rehash_dataclass(
            dispatches[0],
            "dispatch_hash",
            dispatch_adapter_version="m336k12.invalid-adapter.v99",
        )
        operation = changed.verify
    elif number == 31:
        _capsule, historical = _active_capsule(tmp_path)
        operation = lambda: M336K12NativeExecutionCapsuleReceipt.from_dict(
            asdict(historical)
        )
    elif number == 32:
        receipt = verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=binding,
            repository=ROOT,
        )
        forged = _rehash_dataclass(
            receipt,
            "receipt_hash",
            target_mismatch_count=1,
            status="PASS",
        )
        operation = forged.verify
    elif number == 41:
        changed = _rehash_dataclass(
            dispatches[0], "dispatch_hash", execution_scope="HISTORICAL_READ_ONLY"
        )
        operation = changed.verify
    elif number == 42:
        capsule, _historical = _active_capsule(tmp_path)
        changed = _rehash_dataclass(
            capsule,
            "receipt_hash",
            dispatch_contract_hash=content_hash(case),
        )
        operation = changed.verify
    else:
        raise AssertionError(f"unhandled mutation {number}: {case}")

    with pytest.raises(M336K2ProtocolError):
        operation()


def test_m336k12_mutation_suite_shape() -> None:
    assert len(M336K12_MUTATION_CASES) == 42
    assert len(set(M336K12_MUTATION_CASES)) == 42
