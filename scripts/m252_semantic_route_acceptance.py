"""Run the CPU-only M-25.2 semantic route safety acceptance battery."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import SemanticFamily, specification_hash
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import (
    controlled_command,
    install_structural_catalog,
    structural_specs,
)
from ai_brain.stage2.dispatch_validation import (
    expected_final_state,
    validate_all_skill_dispatches,
)
from ai_brain.stage2.equivalence_validation import (
    validate_final_state_equivalence_classes,
)
from ai_brain.stage2.models import (
    ConfirmationDecision,
    EquivalenceScope,
    SearchStatus,
)
from ai_brain.stage2.registry import SkillRegistryStaleError, rebuild_from_rule_memory
from ai_brain.stage2.service import (
    ConfirmationRequiredError,
    SkillDispatchError,
    Stage2Router,
    validate_dispatch_receipt,
    validate_selection_receipt,
)
from ai_brain.stage2.version import (
    SKILL_REGISTRY_SCHEMA_VERSION,
    STAGE2_SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT = ROOT / "runs" / "m252_semantic_route_acceptance.json"


def run(result_path: Path) -> dict:
    started = time.perf_counter()
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    with tempfile.TemporaryDirectory(prefix="ai-brain-m252-") as directory:
        work = Path(directory)
        catalog = install_structural_catalog(work / "catalog")
        memory = RuleMemory.load(catalog.service.memory_path)
        registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
        registry_path = work / "skill_registry_v3.json"
        registry.save(registry_path)
        registry.validate_against_rule_memory(memory)

        require(STAGE2_SCHEMA_VERSION == 3, "Stage-2 schema is not v3")
        require(
            SKILL_REGISTRY_SCHEMA_VERSION == 3,
            "SkillRegistry schema is not v3",
        )
        require(len(registry.active_records()) == 89, "structural catalog changed")

        router = _router(registry, catalog.service.memory_path, work / "exact")
        exact_rows = []
        counter = 0
        for family, sources, destination in structural_specs():
            specification = build_family_specification(
                family, sources=sources, destination=destination
            )
            expected_hash = specification_hash(specification)
            for scope in EquivalenceScope:
                _, result = router.search_final_state_effect(
                    specification,
                    equivalence_scope=scope,
                    query_id_factory=lambda i=counter: f"m252-exact-{i}",
                )
                counter += 1
                require(
                    result.status == SearchStatus.EXACT_MATCH,
                    "installed structural skill was not exact",
                )
                require(result.exact_match, "exact_match was not set")
                require(len(result.candidates) == 1, "exact result was not unique")
                candidate = result.candidates[0]
                require(
                    candidate.specification_hash == expected_hash,
                    "canonical member replaced an exact structural skill",
                )
                require(
                    not candidate.evidence["structural_identity_differs"],
                    "exact evidence claims a structural difference",
                )
                exact_rows.append(
                    {
                        "scope": str(scope),
                        "skill_id": candidate.skill_id,
                        "specification_hash": candidate.specification_hash,
                    }
                )
        require(counter == 178, "exact scope matrix is incomplete")

        controlled_router = _router(
            registry, catalog.service.memory_path, work / "controlled"
        )
        controlled = 0
        cross_language_equal = 0
        for family, sources, destination in structural_specs():
            selected: dict[str, str] = {}
            for language in ("ru", "en"):
                for extended in (False, True):
                    text = controlled_command(
                        family,
                        sources,
                        destination,
                        language,
                        extended=extended,
                    )
                    _, result = controlled_router.search_controlled(
                        text,
                        language,
                        query_id_factory=lambda i=controlled: f"m252-controlled-{i}",
                    )
                    controlled += 1
                    require(
                        result.status == SearchStatus.EXACT_MATCH,
                        "controlled retrieval regressed",
                    )
                    selected[language] = result.candidates[0].skill_id
            cross_language_equal += int(selected["ru"] == selected["en"])
        require(controlled == 356, "controlled matrix is incomplete")
        require(cross_language_equal == 89, "cross-language equality regressed")

        equivalence = validate_final_state_equivalence_classes(
            catalog.service.memory_path, registry
        )
        require(
            equivalence["final_state_effect_class_count"] == 57,
            "final-state class count changed",
        )
        require(
            equivalence["trace_distinct_class_count"] == 16,
            "trace-distinct classes were not identified",
        )

        equivalent_integrations = []
        negative_checks = []
        cases = [
            (
                "merge_two",
                build_family_specification(
                    SemanticFamily.MERGE_TWO,
                    sources=("A", "B"),
                    destination="C",
                ),
                True,
            ),
            (
                "merge_three",
                build_family_specification(
                    SemanticFamily.MERGE_THREE,
                    sources=("A", "B", "C"),
                    destination="D",
                ),
                True,
            ),
            (
                "singleton_noop",
                replace(
                    build_family_specification(SemanticFamily.NOOP),
                    preserve=("A",),
                ),
                False,
            ),
        ]
        for label, requested, remove_exact in cases:
            case_dir = work / label
            case_dir.mkdir()
            case_router, case_registry = _reduced_router(
                catalog,
                registry,
                requested,
                case_dir,
                remove_exact=remove_exact,
            )
            _, full = case_router.search_final_state_effect(
                requested,
                query_id_factory=lambda name=label: f"{name}-full",
            )
            require(full.status == SearchStatus.NO_MATCH, "full trace substituted")
            query, result = case_router.search_final_state_effect(
                requested,
                equivalence_scope=EquivalenceScope.FINAL_STATE_ONLY,
                query_id_factory=lambda name=label: f"{name}-final",
            )
            require(
                result.status == SearchStatus.FINAL_STATE_EQUIVALENT,
                f"{label} did not expose reviewed final-state candidates",
            )
            require(not result.exact_match, "equivalent result was marked exact")
            candidate = result.candidates[0]
            require(
                candidate.specification_hash != result.requested_specification_hash,
                "equivalent candidate is not structurally different",
            )
            pending = case_router.prepare_selection(query, result, candidate.skill_id)
            try:
                case_router.confirm_selection(pending, identity="m252-reviewer")
            except ConfirmationRequiredError:
                negative_checks.append(f"{label}:normal_confirmation_rejected")
            else:
                raise AssertionError("normal confirmation authorized substitution")
            confirmed = case_router.confirm_selection(
                pending,
                identity="m252-reviewer",
                decision=(
                    ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION
                ),
            )
            validate_selection_receipt(confirmed)
            state = {"R0": 2, "R1": 3, "R2": 5, "R3": 7}
            _, execution, dispatch_receipt = case_router.dispatch(
                query=query,
                result=result,
                selection=confirmed,
                proposal=catalog.proposals[candidate.rule_id],
                installed_receipt=catalog.receipts[candidate.rule_id],
                initial_state=state,
            )
            validate_dispatch_receipt(dispatch_receipt, initial_state=state)
            require(
                execution.final_state == expected_final_state(requested, state),
                "equivalent dispatch violated requested final-state semantics",
            )
            require(
                dispatch_receipt.structural_identity_differs,
                "dispatch receipt hid structural difference",
            )
            require(
                not dispatch_receipt.full_trace_equivalent,
                "dispatch receipt overstated trace equivalence",
            )
            events = [item.event_type for item in case_router.audit.replay()]
            for event in (
                "FINAL_STATE_EQUIVALENT_FOUND",
                "EQUIVALENT_SELECTION_REVIEWED",
                "EQUIVALENT_SELECTION_CONFIRMED",
                "EQUIVALENT_SKILL_DISPATCHED",
            ):
                require(event in events, f"missing equivalent audit event {event}")
            equivalent_integrations.append(
                {
                    "case": label,
                    "candidate_count": len(result.candidates),
                    "requested_specification_hash": (
                        result.requested_specification_hash
                    ),
                    "selected_specification_hash": candidate.specification_hash,
                    "equivalence_class_hash": confirmed.equivalence_class_hash,
                    "final_state": execution.final_state,
                    "dispatch_hash": dispatch_receipt.dispatch_hash,
                    "audit_events": events,
                    "active_case_skill_count": len(case_registry.active_records()),
                }
            )

            for field, value in (
                ("equivalence_scope", EquivalenceScope.FULL_EXECUTION_TRACE),
                ("requested_specification_hash", "0" * 64),
                ("selected_specification_hash", "1" * 64),
                ("equivalence_class_hash", "2" * 64),
            ):
                try:
                    validate_selection_receipt(replace(confirmed, **{field: value}))
                except SkillDispatchError:
                    negative_checks.append(f"{label}:{field}_tamper_rejected")
                else:
                    raise AssertionError(f"{field} tamper was accepted")

        drop = build_family_specification(
            SemanticFamily.DROP_THEN_TRANSFER,
            sources=("A", "B"),
            destination="C",
        )
        drop_dir = work / "drop-negative"
        drop_dir.mkdir()
        drop_router, _ = _reduced_router(
            catalog, registry, drop, drop_dir, remove_exact=True
        )
        for index, scope in enumerate(EquivalenceScope):
            _, result = drop_router.search_final_state_effect(
                drop,
                equivalence_scope=scope,
                query_id_factory=lambda i=index: f"drop-negative-{i}",
            )
            require(result.status == SearchStatus.NO_MATCH, "DROP was substituted")
            negative_checks.append(f"drop:{scope}:substitution_rejected")

        stale_dir = work / "stale-membership"
        stale_dir.mkdir()
        stale_requested = cases[0][1]
        stale_router, _ = _reduced_router(
            catalog,
            registry,
            stale_requested,
            stale_dir,
            remove_exact=True,
        )
        stale_query, stale_result = stale_router.search_final_state_effect(
            stale_requested,
            equivalence_scope=EquivalenceScope.FINAL_STATE_ONLY,
        )
        stale_candidate = stale_result.candidates[0]
        stale_selection = stale_router.confirm_selection(
            stale_router.prepare_selection(
                stale_query, stale_result, stale_candidate.skill_id
            ),
            identity="m252-reviewer",
            decision=ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION,
        )
        changed_memory = RuleMemory.load(stale_router.memory_path)
        changed_memory.deprecate(stale_candidate.rule_id)
        changed_memory.save(stale_router.memory_path)
        try:
            stale_router.dispatch(
                query=stale_query,
                result=stale_result,
                selection=stale_selection,
                proposal=catalog.proposals[stale_candidate.rule_id],
                installed_receipt=catalog.receipts[stale_candidate.rule_id],
                initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7},
            )
        except SkillRegistryStaleError:
            negative_checks.append("merge_two:stale_membership_rejected")
        else:
            raise AssertionError("stale equivalence membership was accepted")
        require(
            "EQUIVALENT_SKILL_DISPATCH_FAILED"
            in [item.event_type for item in stale_router.audit.replay()],
            "equivalent dispatch failure was not audited",
        )

        full_dispatch = validate_all_skill_dispatches(catalog, registry, work)
        require(
            full_dispatch["structural_dispatch_success"] == 89,
            "full structural dispatch regressed",
        )
        require(
            full_dispatch["controlled_ru_en_dispatch_success"] == 12,
            "controlled dispatch smoke regressed",
        )

        no_torch = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ai_brain.stage2; assert 'torch' not in sys.modules",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        require(no_torch.returncode == 0, "trusted import loaded torch")

    result = {
        "milestone": "M-25.2",
        "status": "PASS",
        "outcome": "OUTCOME_A",
        "git_sha": _git("rev-parse", "HEAD"),
        "platform": platform.platform(),
        "python": sys.version,
        "checks": checks,
        "schema": {
            "stage2": STAGE2_SCHEMA_VERSION,
            "skill_registry": SKILL_REGISTRY_SCHEMA_VERSION,
            "v2_policy": "REBUILD_FROM_VERIFIED_RULE_MEMORY",
        },
        "exact_scope_matrix": {
            "success": len(exact_rows),
            "total": 178,
            "structurally_different_returned_as_exact": 0,
        },
        "controlled_retrieval": {
            "success": controlled,
            "total": 356,
            "cross_language_equality": cross_language_equal / 89,
        },
        "equivalence_validation": equivalence,
        "equivalent_integrations": equivalent_integrations,
        "negative_checks": negative_checks,
        "dispatch": {
            "structural_success": full_dispatch["structural_dispatch_success"],
            "structural_total": full_dispatch["structural_dispatch_total"],
            "controlled_success": full_dispatch["controlled_ru_en_dispatch_success"],
            "controlled_total": full_dispatch["controlled_ru_en_dispatch_total"],
        },
        "unsafe_automatic_selections": 0,
        "learned_semantic_authority": 0,
        "trusted_import_no_torch": True,
        "duration_seconds": time.perf_counter() - started,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _router(registry, memory_path: Path, work: Path) -> Stage2Router:
    work.mkdir(parents=True, exist_ok=True)
    return Stage2Router(
        registry=registry,
        memory_path=memory_path,
        stage1_audit_path=work / "stage1_audit.jsonl",
        stage2_audit_path=work / "stage2_audit.jsonl",
    )


def _reduced_router(
    catalog,
    registry,
    requested,
    work: Path,
    *,
    remove_exact: bool,
):
    memory = RuleMemory.load(catalog.service.memory_path)
    if remove_exact:
        requested_hash = specification_hash(requested)
        exact = next(
            item
            for item in registry.active_records()
            if item.specification_hash == requested_hash
        )
        memory.deprecate(exact.rule_id)
    memory_path = work / "rule_memory.json"
    memory.save(memory_path)
    reduced = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
    return _router(reduced, memory_path, work), reduced


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    args = parser.parse_args()
    print(json.dumps(run(args.result), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
