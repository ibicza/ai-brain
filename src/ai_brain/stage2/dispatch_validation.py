"""Complete trusted dispatch validation for the frozen structural catalog."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import content_hash
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import (
    InstalledCatalog,
    controlled_command,
    structural_specs,
)
from ai_brain.stage2.models import SearchStatus
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage2.service import (
    Stage2Router,
    validate_dispatch_receipt,
    validate_selection_receipt,
)

_REGISTER = {"A": "R0", "B": "R1", "C": "R2", "D": "R3"}


def validate_all_skill_dispatches(
    catalog: InstalledCatalog,
    registry: SkillRegistry,
    work_dir: Path,
) -> dict:
    """Dispatch every structural skill and a per-family state/language battery."""
    router = Stage2Router(
        registry=registry,
        memory_path=catalog.service.memory_path,
        stage1_audit_path=catalog.service.audit.path,
        stage2_audit_path=work_dir / "all_skill_dispatch_audit.jsonl",
    )
    rows = list(structural_specs())
    family_representatives = {}
    full_rows: list[dict] = []
    for index, (family, sources, destination) in enumerate(rows):
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )
        family_representatives.setdefault(family, (sources, destination))
        initial_state = {"R0": 2, "R1": 3, "R2": 5, "R3": 7}
        full_rows.append(
            _dispatch_and_validate(
                router,
                catalog,
                specification,
                initial_state,
                query_id=f"m251-all-{index}",
            )
        )

    batteries: list[dict] = []
    controlled: list[dict] = []
    for family_index, (family, (sources, destination)) in enumerate(
        family_representatives.items()
    ):
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )
        for state_index, (label, state) in enumerate(
            _state_battery(sources, destination, specification.preserve)
        ):
            row = _dispatch_and_validate(
                router,
                catalog,
                specification,
                state,
                query_id=f"m251-battery-{family_index}-{state_index}",
            )
            batteries.append({**row, "state_case": label})
        for language in ("ru", "en"):
            text = controlled_command(family, sources, destination, language)
            query, result = router.search_controlled(
                text,
                language,
                query_id_factory=lambda f=family.value, lang=language: (
                    f"m251-controlled-dispatch-{f}-{lang}"
                ),
            )
            controlled.append(
                _dispatch_result(
                    router,
                    catalog,
                    query,
                    result,
                    specification,
                    {"R0": 2, "R1": 3, "R2": 5, "R3": 7},
                )
            )

    family_counts = Counter(item["family"] for item in full_rows)
    return {
        "status": "PASS",
        "structural_dispatch_success": len(full_rows),
        "structural_dispatch_total": len(rows),
        "family_counts": dict(family_counts),
        "representative_state_checks": len(batteries),
        "controlled_ru_en_dispatch_success": len(controlled),
        "controlled_ru_en_dispatch_total": len(family_representatives) * 2,
        "rows": full_rows,
        "representative_battery": batteries,
        "controlled_rows": controlled,
    }


def expected_final_state(
    specification: ProgramSpecification, initial_state: dict[str, int]
) -> dict[str, int]:
    expected = dict(initial_state)
    for action, source, destination in specification.phase_constraints:
        source_register = _REGISTER[source]
        if action == "DROP_ONE":
            expected[source_register] = 0
        elif action == "MOVE_ONE" and destination is not None:
            destination_register = _REGISTER[destination]
            expected[destination_register] += expected[source_register]
            expected[source_register] = 0
        else:
            raise AssertionError(f"unexpected phase {action}")
    return expected


def _dispatch_and_validate(
    router: Stage2Router,
    catalog: InstalledCatalog,
    specification: ProgramSpecification,
    initial_state: dict[str, int],
    *,
    query_id: str,
) -> dict:
    query, result = router.search_structured(
        specification, query_id_factory=lambda: query_id
    )
    return _dispatch_result(
        router, catalog, query, result, specification, initial_state
    )


def _dispatch_result(
    router: Stage2Router,
    catalog: InstalledCatalog,
    query,
    result,
    specification: ProgramSpecification,
    initial_state: dict[str, int],
) -> dict:
    if result.status != SearchStatus.EXACT_MATCH or len(result.candidates) != 1:
        raise AssertionError("trusted retrieval did not return one exact skill")
    candidate = result.candidates[0]
    pending = router.prepare_selection(query, result, candidate.skill_id)
    validate_selection_receipt(pending)
    confirmed = router.confirm_selection(pending, identity="m251-dispatch-validator")
    validate_selection_receipt(confirmed)
    _, execution, dispatch = router.dispatch(
        query=query,
        result=result,
        selection=confirmed,
        proposal=catalog.proposals[candidate.rule_id],
        installed_receipt=catalog.receipts[candidate.rule_id],
        initial_state=initial_state,
    )
    validate_dispatch_receipt(dispatch, initial_state=initial_state)
    expected = expected_final_state(specification, initial_state)
    if execution.final_state != expected:
        raise AssertionError(
            f"final state mismatch: expected={expected}, actual={execution.final_state}"
        )
    if not execution.halted:
        raise AssertionError("Stage-1 execution did not halt")
    if candidate.rule_id != execution.rule_id or dispatch.rule_id != candidate.rule_id:
        raise AssertionError("selected and executed rule IDs differ")
    if dispatch.rule_semantic_hash != candidate.rule_semantic_hash:
        raise AssertionError("dispatch semantic hash differs from selection")
    for role in specification.preserve:
        register = _REGISTER[role]
        if execution.final_state[register] != initial_state[register]:
            raise AssertionError(f"preserved role changed: {role}")
    return {
        "family": str(specification_family(specification)),
        "skill_id": candidate.skill_id,
        "rule_id_hash": content_hash(candidate.rule_id),
        "rule_semantic_hash": candidate.rule_semantic_hash,
        "selection_receipt_hash": confirmed.receipt_hash,
        "dispatch_receipt_hash": dispatch.dispatch_hash,
        "stage1_execution_hash": execution.execution_hash,
        "halted": execution.halted,
        "initial_state": initial_state,
        "final_state": execution.final_state,
    }


def specification_family(specification: ProgramSpecification):
    from ai_brain.stage1.specifications import infer_family

    family = infer_family(specification)
    if family is None:
        raise AssertionError("catalog specification has no family")
    return family


def _state_battery(
    sources: tuple[str, ...], destination: str | None, preserve: tuple[str, ...]
) -> tuple[tuple[str, dict[str, int]], ...]:
    states: list[tuple[str, dict[str, int]]] = [
        ("all_zero", {"R0": 0, "R1": 0, "R2": 0, "R3": 0}),
        ("multiple_active", {"R0": 2, "R1": 3, "R2": 5, "R3": 7}),
    ]
    one_source = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}
    if sources:
        one_source[_REGISTER[sources[0]]] = 1
    states.append(("one_active_source", one_source))
    destination_nonzero = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}
    if destination:
        destination_nonzero[_REGISTER[destination]] = 9
    if sources:
        destination_nonzero[_REGISTER[sources[0]]] = 2
    states.append(("destination_nonzero", destination_nonzero))
    preserved_nonzero = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}
    if preserve:
        preserved_nonzero[_REGISTER[preserve[0]]] = 11
    if sources:
        preserved_nonzero[_REGISTER[sources[0]]] = 2
    states.append(("preserved_nonzero", preserved_nonzero))
    for count in (10, 100):
        state = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}
        if sources:
            state[_REGISTER[sources[0]]] = count
        states.append((f"count_{count}", state))
    return tuple(states)
