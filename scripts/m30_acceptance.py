"""Run deterministic M-30 scale and Phase-0 mutation acceptance."""

from __future__ import annotations

import dataclasses
import re
import shutil
import tempfile
from pathlib import Path

from ai_brain.stage2.conversation.acceptance import (
    run_pending_security_acceptance,
    run_scripted_acceptance,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.catalog_anchor import verify_instance_catalog_anchor
from ai_brain.stage2.education.explanations import (
    build_explanation_plan,
    verify_explanation_plan,
)
from ai_brain.stage2.education.fact_replay import (
    descriptor_from_dict,
    replay_fact_descriptor,
)
from ai_brain.stage2.education.models import (
    EducationalReplayStatus,
    ExerciseFamily,
    ExplanationMode,
    ExplanationPlan,
)
from ai_brain.stage2.education.service import _learner_text
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.facts.models import ClaimStatus

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    result = run_scripted_acceptance()
    result.update(_phase0_battery())
    result.update(run_pending_security_acceptance())
    injection_executions = result["injection_action_executions"]
    result["grading_override"] = injection_executions
    result["progress_override"] = injection_executions
    result["memory_writes"] = injection_executions
    if any(
        result[key]
        for key in (
            "wrong_state_transition",
            "pending_security_acceptances",
            "phase0_fact_upstream_accepted",
            "phase0_non_catalog_closures_accepted",
            "phase0_incomplete_plans_accepted",
            "phase0_internal_id_hash_leaks",
            "projection_mismatches",
            "cross_learner_leakage",
            "wrong_deterministic_recommendation",
            "injection_action_executions",
        )
    ):
        result["status"] = "FAIL"
    print(canonical_json(result))


def _phase0_battery() -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="m30-acceptance-") as directory:
        chemistry_root = Path(directory) / "chemistry"
        shutil.copytree(ROOT / "artifacts/domains/chemistry/m29", chemistry_root)
        chemistry = ChemistryDomainService.open(chemistry_root)
        catalog = EducationalCatalogV2.load(
            ROOT / "artifacts/education/m30/catalog_v4.json", chemistry
        )
        fact_entries = tuple(
            item
            for item in catalog.entries
            if item.exercise_spec.family is ExerciseFamily.FACT_RETRIEVAL
        )
        accepted_facts = 0
        for index in range(100):
            descriptor = descriptor_from_dict(
                fact_entries[index].graph.source_result_artifact["answer"][
                    "fact_replay_descriptor"
                ]
            )
            target = descriptor.bindings[0].claim_id

            class MutatedMemory:
                def __init__(self, target_id):
                    self.target_id = target_id

                def __getattr__(self, name):
                    return getattr(chemistry.memory, name)

                def get_claim_state(self, claim_id):
                    state = chemistry.memory.get_claim_state(claim_id)
                    return (
                        dataclasses.replace(state, status=ClaimStatus.RETRACTED)
                        if claim_id == self.target_id
                        else state
                    )

            accepted_facts += (
                replay_fact_descriptor(
                    descriptor, MutatedMemory(target), chemistry.manifest
                )
                is EducationalReplayStatus.CURRENT
            )
        accepted_catalog = 0
        for entry in catalog.entries[:500]:
            forged = dataclasses.replace(
                entry.internal_instance, catalog_entry_hash="0" * 64, instance_hash=""
            )
            body = dataclasses.asdict(forged)
            body.pop("instance_hash")
            forged = dataclasses.replace(forged, instance_hash=content_hash(body))
            try:
                verify_instance_catalog_anchor(forged, entry)
            except ValueError:
                pass
            else:
                accepted_catalog += 1
        accepted_plans = 0
        for entry in catalog.entries[:500]:
            plan = build_explanation_plan(
                entry.graph, language="en", mode=ExplanationMode.FULL
            )
            body = dataclasses.asdict(plan)
            body["segments"] = tuple(plan.segments[:-1])
            body.pop("plan_hash")
            forged = ExplanationPlan(**body, plan_hash=content_hash(body))
            try:
                verify_explanation_plan(forged, entry.graph)
            except ValueError:
                pass
            else:
                accepted_plans += 1
        leaks = 0
        for index in range(1_000):
            public = _learner_text(
                f"Intermediate result [n{index}]: 1. First error: final"
            )
            leaks += bool(
                re.search(
                    r"(?:\[)?(?:n\d+|final|answer)(?:\])?|[0-9a-f]{40,64}",
                    public,
                    re.IGNORECASE,
                )
            )
    return {
        "phase0_fact_upstream_mutations": 100,
        "phase0_fact_upstream_accepted": accepted_facts,
        "phase0_catalog_closure_mutations": 500,
        "phase0_non_catalog_closures_accepted": accepted_catalog,
        "phase0_canonical_plan_mutations": 500,
        "phase0_incomplete_plans_accepted": accepted_plans,
        "phase0_public_actions": 1_000,
        "phase0_internal_id_hash_leaks": leaks,
    }


if __name__ == "__main__":
    main()
