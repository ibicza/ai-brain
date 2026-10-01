from __future__ import annotations

import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_startup_policy,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12NativeStagePlanBinding,
    build_m336k12_native_execution_plan,
    build_m336k12_native_stage_dispatches,
    verify_m336k12_native_stage_plan,
)
from ai_brain.stage3.acquisition.m336k13_plan import (
    M336K13NativeStagePlanBinding,
    project_m336k13_native_stage_plan_binding_to_v12,
    verify_m336k13_native_stage_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def _closure(tmp_path: Path):
    dispatches = build_m336k12_native_stage_dispatches(
        repository=ROOT,
        execution_scope="OFFICIAL_CONTROLLER",
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
    base = M336K12NativeStagePlanBinding.build(
        repository=ROOT,
        exact_implementation_tip="a" * 40,
        active_profile_hash="c" * 64,
        route_registry_hash="b" * 64,
        typed_route_manifest_hash="d" * 64,
        dispatches=dispatches,
        python_executable=Path(sys.executable),
        outer_startup_policy_hash=build_m336k5_python_startup_policy().policy_hash,
        native_capsule_receipt_hash="e" * 64,
    )
    final_plan_binding_hash = "f" * 64
    active = M336K13NativeStagePlanBinding.build(base, final_plan_binding_hash)
    return dispatches, plan, base, active, final_plan_binding_hash


def _rehash_active(
    value: M336K13NativeStagePlanBinding, **changes: object
) -> M336K13NativeStagePlanBinding:
    changed = replace(value, **changes, plan_binding_hash="0" * 64)
    return replace(changed, plan_binding_hash=content_hash(changed._body()))


def test_v6_verification_projects_once_and_rebinds_active_parity(
    tmp_path: Path,
) -> None:
    dispatches, plan, base, active, final_hash = _closure(tmp_path)

    parity = verify_m336k13_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=active,
        expected_base_plan_binding=base,
        expected_final_controller_plan_binding_receipt_hash=final_hash,
        repository=ROOT,
    )
    base_parity = verify_m336k12_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=base,
        repository=ROOT,
    )

    assert project_m336k13_native_stage_plan_binding_to_v12(active) == base
    assert parity.native_stage_plan_binding_hash == active.plan_binding_hash
    assert {
        name
        for name, value in base_parity.canonical_object().items()
        if parity.canonical_object()[name] != value
    } == {"native_stage_plan_binding_hash", "receipt_hash"}


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("exact_implementation_tip", "1" * 40),
        ("active_profile_hash", "1" * 64),
        ("route_registry_hash", "2" * 64),
        ("typed_route_manifest_hash", "3" * 64),
        ("python_executable_bytes_hash", "4" * 64),
        ("plan_builder_source_hash", "5" * 64),
        ("consumer_source_hash", "6" * 64),
        ("legacy_adapter_source_hash", "7" * 64),
        ("outer_startup_policy_hash", "8" * 64),
        ("powershell_launcher_source_hash", "9" * 64),
        ("bootstrap_source_hash", "a" * 64),
        ("stage_worker_source_hash", "b" * 64),
        ("native_capsule_receipt_hash", "c" * 64),
        ("preledger_admission_policy_hash", "d" * 64),
    ],
)
def test_v6_rejects_fully_rehashed_semantic_base_mutations(
    tmp_path: Path, field_name: str, replacement: str
) -> None:
    dispatches, plan, base, active, final_hash = _closure(tmp_path)
    mutated = _rehash_active(active, **{field_name: replacement})
    mutated.verify()

    with pytest.raises(M336K2ProtocolError, match="base projection changed"):
        verify_m336k13_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=mutated,
            expected_base_plan_binding=base,
            expected_final_controller_plan_binding_receipt_hash=final_hash,
            repository=ROOT,
        )


def test_v6_rejects_fully_rehashed_final_controller_binding_mutation(
    tmp_path: Path,
) -> None:
    dispatches, plan, base, active, final_hash = _closure(tmp_path)
    mutated = _rehash_active(
        active, final_controller_plan_binding_receipt_hash="1" * 64
    )
    mutated.verify()

    with pytest.raises(M336K2ProtocolError, match="final-controller binding changed"):
        verify_m336k13_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=mutated,
            expected_base_plan_binding=base,
            expected_final_controller_plan_binding_receipt_hash=final_hash,
            repository=ROOT,
        )


def test_v6_rejects_noncanonical_base_shape_before_v5_verification(
    tmp_path: Path,
) -> None:
    dispatches, plan, base, active, final_hash = _closure(tmp_path)
    mutated = _rehash_active(active, bootstrap_repository_path="scripts/foreign.py")
    mutated.verify()

    with pytest.raises(
        M336K2ProtocolError, match="M336K12 native stage plan binding is invalid"
    ):
        verify_m336k13_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=mutated,
            expected_base_plan_binding=base,
            expected_final_controller_plan_binding_receipt_hash=final_hash,
            repository=ROOT,
        )


def test_v6_rejects_v5_input_unknown_field_and_foreign_subclass(
    tmp_path: Path,
) -> None:
    dispatches, plan, base, active, final_hash = _closure(tmp_path)

    with pytest.raises(M336K2ProtocolError, match="binding type changed"):
        verify_m336k13_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=base,  # type: ignore[arg-type]
            expected_base_plan_binding=base,
            expected_final_controller_plan_binding_receipt_hash=final_hash,
            repository=ROOT,
        )

    unknown = {**active.canonical_object(), "unknown_extension": "0" * 64}
    with pytest.raises(M336K2ProtocolError, match="fields changed"):
        M336K13NativeStagePlanBinding.from_dict(unknown)

    class ForeignBinding(M336K13NativeStagePlanBinding):
        pass

    foreign = ForeignBinding(**asdict(active))
    with pytest.raises(M336K2ProtocolError, match="binding type changed"):
        project_m336k13_native_stage_plan_binding_to_v12(foreign)


def test_v5_verification_behavior_remains_unchanged(tmp_path: Path) -> None:
    dispatches, plan, base, _active, _final_hash = _closure(tmp_path)

    parity = verify_m336k12_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=base,
        repository=ROOT,
    )
    changed = replace(
        base, plan_builder_source_hash="0" * 64, plan_binding_hash="0" * 64
    )
    changed = replace(changed, plan_binding_hash=content_hash(changed._body()))

    assert parity.native_stage_plan_binding_hash == base.plan_binding_hash
    with pytest.raises(M336K2ProtocolError, match="live plan binding changed"):
        verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=dispatches,
            plan_binding=changed,
            repository=ROOT,
        )
