from __future__ import annotations

import dataclasses
import re
import shutil
from pathlib import Path

import pytest

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education import models
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
from ai_brain.stage2.education.service import EducationalService, _learner_text
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.values import FactValue

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY_ROOT = ROOT / "artifacts" / "domains" / "chemistry" / "m29"
CATALOG_PATH = ROOT / "artifacts" / "education" / "m30" / "catalog_v4.json"


@pytest.fixture(scope="module")
def catalog(tmp_path_factory) -> EducationalCatalogV2:
    chemistry_root = tmp_path_factory.mktemp("m30-phase0") / "chemistry"
    shutil.copytree(CHEMISTRY_ROOT, chemistry_root)
    chemistry = ChemistryDomainService.open(chemistry_root)
    catalog = EducationalCatalogV2.load(CATALOG_PATH, chemistry)
    catalog._m30_test_chemistry = chemistry
    catalog._m30_test_manifest = chemistry.manifest
    return catalog


def test_phase0_requires_explicit_fact_replay_statuses() -> None:
    values = {item.value for item in models.EducationalReplayStatus}
    assert {"STALE_DERIVATION", "STALE_FACT_VALUE"} <= values


def test_phase0_catalog_entries_and_sessions_have_exact_anchor() -> None:
    assert "catalog_entry_hash" in models.ExerciseInstance.__dataclass_fields__
    assert "catalog_entry_hash" in models.TutorSession.__dataclass_fields__
    assert hasattr(EducationalCatalogV2, "by_entry_hash")


def test_phase0_full_plan_rejects_a_rehashed_omission(catalog) -> None:
    graph = catalog.entries[0].graph
    plan = build_explanation_plan(graph, language="en", mode=ExplanationMode.FULL)
    segments = tuple(
        segment for segment in plan.segments if segment.kind.value != "FINAL_RESULT"
    )
    body = {
        **dataclasses.asdict(plan),
        "segments": segments,
    }
    body.pop("plan_hash")
    forged = ExplanationPlan(**body, plan_hash=content_hash(body))
    with pytest.raises(ValueError, match="canonical"):
        verify_explanation_plan(forged, graph)


@pytest.mark.parametrize(
    "text",
    (
        "First error: n17",
        "Первая ошибка: final",
        "Intermediate result [n4]: 12.5 g/mol.",
        "Промежуточный результат [answer]: 8.",
    ),
)
def test_phase0_public_text_removes_internal_node_ids(text: str) -> None:
    public = _learner_text(text)
    assert not re.search(r"(?:\[)?(?:n\d+|final|answer)(?:\])?", public)


def test_phase0_requires_opaque_public_pending_action_types() -> None:
    assert hasattr(models, "PublicPendingActionHandle")
    assert hasattr(models, "PublicPreparedAction")


def test_phase0_authority_result_separates_history_and_currentness() -> None:
    assert hasattr(models, "EducationalHistoryStatus")


def test_phase0_rehashed_non_catalog_variant_is_rejected(catalog) -> None:
    entry = catalog.entries[0]
    forged = dataclasses.replace(
        entry.internal_instance, catalog_entry_hash="0" * 64, instance_hash=""
    )
    body = dataclasses.asdict(forged)
    body.pop("instance_hash")
    forged = dataclasses.replace(forged, instance_hash=content_hash(body))
    with pytest.raises(ValueError, match="another catalog entry"):
        verify_instance_catalog_anchor(forged, entry)


def test_phase0_fact_replay_detects_current_value_change(catalog, monkeypatch) -> None:
    entry = next(
        item
        for item in catalog.entries
        if item.exercise_spec.family is ExerciseFamily.FACT_RETRIEVAL
    )
    artifact = entry.graph.source_result_artifact["given"]
    descriptor = descriptor_from_dict(artifact["fact_replay_descriptor"])
    memory = (
        catalog._m30_test_chemistry.memory
        if hasattr(catalog, "_m30_test_chemistry")
        else None
    )
    assert memory is not None
    original = memory.get_claim_state

    def changed(claim_id):
        state = original(claim_id)
        if claim_id != descriptor.bindings[0].claim_id:
            return state
        value = FactValue.create(
            state.record.object_value.kind, "999", unit=state.record.object_value.unit
        )
        return dataclasses.replace(
            state, record=dataclasses.replace(state.record, object_value=value)
        )

    monkeypatch.setattr(memory, "get_claim_state", changed)
    assert (
        replay_fact_descriptor(descriptor, memory, catalog._m30_test_manifest)
        is EducationalReplayStatus.STALE_FACT_VALUE
    )


def test_phase0_stale_history_remains_backup_eligible(tmp_path, monkeypatch) -> None:
    chemistry_root = tmp_path / "chemistry"
    shutil.copytree(CHEMISTRY_ROOT, chemistry_root)
    service = EducationalService.open(
        chemistry_root, tmp_path / "sessions", catalog_path=CATALOG_PATH
    )
    service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=3,
        language="en",
        session_id="m30-history",
        created_at="2026-01-01T00:00:00Z",
    )
    monkeypatch.setitem(
        service.chemistry.manifest, "fact_memory_snapshot_hash", "0" * 64
    )
    result = service.backup(tmp_path / "history.sqlite3")
    authority = result["verification"]["educational_store_authority"]
    assert authority["history_status"] == "HISTORY_VALID"
    assert authority["current_authority_status"] == "STALE_WITH_HISTORY_VALID"
