from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import SemanticFamily, content_hash
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import (
    controlled_command,
    install_structural_catalog,
    structural_specs,
)
from ai_brain.stage2.dataset import (
    generate_query_dataset,
    load_jsonl,
    model_visible_text,
    verify_blind_freeze,
)
from ai_brain.stage2.models import (
    ConfirmationDecision,
    RetrievalMode,
    SearchStatus,
)
from ai_brain.stage2.registry import (
    SkillRegistry,
    SkillRegistryIntegrityError,
    SkillRegistryRecoveryRequiredError,
    SkillRegistryStaleError,
    rebuild_from_rule_memory,
    recover_skill_registry,
)
from ai_brain.stage2.retrieval import candidate_list_hash
from ai_brain.stage2.service import (
    ConfirmationRequiredError,
    SkillDispatchError,
    Stage2Router,
    validate_dispatch_receipt,
    validate_selection_receipt,
)
from ai_brain.stage2.version import (
    EXPECTED_STAGE1_RELEASE_COMMIT,
    EXPECTED_STAGE1_VERSION,
    ensure_stage1_compatible,
)


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):
    directory = tmp_path_factory.mktemp("m25-catalog")
    installed = install_structural_catalog(directory)
    memory = RuleMemory.load(installed.service.memory_path)
    registry = rebuild_from_rule_memory(memory, receipts=installed.receipts)
    registry_path = directory / "registry.json"
    registry.save(registry_path)
    return directory, installed, memory, registry, registry_path


def _router(catalog, suffix: str = "main") -> Stage2Router:
    directory, installed, _, registry, _ = catalog
    return Stage2Router(
        registry=registry,
        memory_path=installed.service.memory_path,
        stage1_audit_path=installed.service.audit.path,
        stage2_audit_path=directory / f"stage2-{suffix}.jsonl",
    )


def test_release_dependency_guard() -> None:
    ensure_stage1_compatible()
    assert EXPECTED_STAGE1_VERSION == "1.0.1"
    assert EXPECTED_STAGE1_RELEASE_COMMIT == (
        "4e9520a16bd3aeb7579ea92ce44060fd7f1a705a"
    )


def test_release_dependency_guard_rejects_incompatible_version(monkeypatch) -> None:
    from ai_brain.stage2 import version

    monkeypatch.setattr(version, "STAGE1_VERSION", "9.9.9")
    with pytest.raises(version.IncompatibleStage1Error):
        version.ensure_stage1_compatible()


def test_registry_builds_exactly_89_verified_skills(catalog) -> None:
    _, _, memory, registry, _ = catalog
    assert len(memory.active_records()) == 89
    assert len(registry.records) == 89
    assert len(registry.active_records()) == 89
    assert len({item.rule_semantic_hash for item in registry.active_records()}) == 89
    assert sum(registry.manifest.family_counts.values()) == 89
    registry.validate_against_rule_memory(memory)


def test_registry_strict_roundtrip_checksum_backup_and_recovery(
    catalog, tmp_path: Path
) -> None:
    _, _, memory, registry, _ = catalog
    path = tmp_path / "registry.json"
    registry.save(path)
    loaded = SkillRegistry.load(path)
    assert loaded.records == registry.records
    updated = registry.update_skill_metadata(
        next(iter(registry.records)), aliases_en=("safe metadata alias",)
    )
    updated.validate_against_rule_memory(memory)
    updated.save(path)
    path.write_bytes(b"{corrupt\xff")
    recovered_read = SkillRegistry.load_with_backup(path)
    assert recovered_read.recovery_source.startswith("backup:")
    with pytest.raises(SkillRegistryRecoveryRequiredError):
        recovered_read.save(path)
    evidence = recover_skill_registry(path)
    assert Path(evidence["preserved_corrupt_primary"]).read_bytes() == b"{corrupt\xff"
    SkillRegistry.load(path).validate_against_rule_memory(memory)

    row = json.loads(path.read_text(encoding="utf-8"))
    row["extra"] = True
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(SkillRegistryIntegrityError):
        SkillRegistry.load(path)


def test_all_structured_specifications_retrieve_exactly(catalog) -> None:
    router = _router(catalog, "structured")
    selected: set[str] = set()
    for index, (family, sources, destination) in enumerate(structural_specs()):
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )
        _, result = router.search_structured(
            specification, query_id_factory=lambda i=index: f"structured-{i}"
        )
        assert result.status == SearchStatus.EXACT_MATCH
        assert result.exact_match
        assert len(result.candidates) == 1
        selected.add(result.candidates[0].skill_id)
    assert len(selected) == 89


def test_exact_semantic_signature_retrieval_is_trusted(catalog) -> None:
    router = _router(catalog, "semantic")
    specification = build_family_specification(
        SemanticFamily.DROP_THEN_TRANSFER,
        sources=("A", "B"),
        destination="C",
    )
    _, result = router.search_semantic_signature(specification)
    assert result.status == SearchStatus.EXACT_MATCH
    assert result.retrieval_mode == RetrievalMode.EXACT_SEMANTIC


def test_all_356_controlled_cases_and_cross_language_equality(catalog) -> None:
    router = _router(catalog, "controlled")
    counter = 0
    for family, sources, destination in structural_specs():
        language_skills: dict[str, str] = {}
        for language in ("ru", "en"):
            for extended in (False, True):
                text = controlled_command(
                    family, sources, destination, language, extended=extended
                )
                _, result = router.search_controlled(
                    text,
                    language,
                    query_id_factory=lambda i=counter: f"controlled-{i}",
                )
                counter += 1
                assert result.status == SearchStatus.EXACT_MATCH
                assert result.retrieval_mode == RetrievalMode.CONTROLLED_EXACT
                language_skills[language] = result.candidates[0].skill_id
        assert language_skills["ru"] == language_skills["en"]
    assert counter == 356


@pytest.mark.parametrize(
    ("text", "language", "status"),
    [
        ("Move every item from A; stop when A is empty.", "en", SearchStatus.AMBIGUOUS),
        (
            "Move every item from A into B; leave A unchanged; stop when A is empty.",
            "en",
            SearchStatus.CONTRADICTORY,
        ),
        ("Multiply A by B and store it in C.", "en", SearchStatus.UNSUPPORTED),
        ("Move A into register E.", "en", SearchStatus.UNSUPPORTED),
        ("Deplacer A vers B.", "fr", SearchStatus.UNSUPPORTED),
    ],
)
def test_unknown_ambiguous_and_unsupported_never_exact(
    catalog, text: str, language: str, status: SearchStatus
) -> None:
    router = _router(catalog, f"negative-{content_hash(text)[:8]}")
    _, result = router.search_controlled(text, language)
    assert result.status == status
    assert not result.exact_match
    assert not result.candidates
    if result.status == SearchStatus.AMBIGUOUS:
        assert result.clarification_target
        assert result.clarification_question


def test_assistive_retrieval_is_candidate_only_and_abstains(catalog) -> None:
    router = _router(catalog, "assistive")
    _, result = router.search_assistive(
        "Please move all items from A to B and preserve C and D", "en"
    )
    assert result.status == SearchStatus.CANDIDATES
    assert result.candidates
    assert not result.exact_match
    _, unknown = router.search_assistive("Sort and multiply the registers", "en")
    assert unknown.status == SearchStatus.NO_MATCH
    assert not unknown.exact_match


def test_identical_queries_have_unique_ids_and_equal_input_hashes(catalog) -> None:
    router = _router(catalog, "query-ids")
    first, _ = router.search_assistive("Move A to B", "en")
    second, _ = router.search_assistive("Move A to B", "en")
    assert first.query_id != second.query_id
    assert first.original_input_hash == second.original_input_hash


def test_counterfactual_near_neighbors_change_exact_skill(catalog) -> None:
    router = _router(catalog, "counterfactual")
    specifications = (
        build_family_specification(
            SemanticFamily.DRAIN, sources=("A",), destination="B"
        ),
        build_family_specification(
            SemanticFamily.DRAIN, sources=("A",), destination="C"
        ),
        build_family_specification(
            SemanticFamily.DRAIN, sources=("B",), destination="A"
        ),
        build_family_specification(
            SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
        ),
        build_family_specification(
            SemanticFamily.DROP_THEN_TRANSFER,
            sources=("A", "B"),
            destination="C",
        ),
    )
    skills = {
        router.search_structured(specification)[1].candidates[0].skill_id
        for specification in specifications
    }
    assert len(skills) == len(specifications)


def test_stale_and_deprecated_registry_fails_closed(catalog) -> None:
    _, _, memory, registry, _ = catalog
    changed = RuleMemory()
    changed.records = dict(memory.records)
    changed.deprecate(next(iter(changed.records)))
    with pytest.raises(SkillRegistryStaleError):
        registry.validate_against_rule_memory(changed)


def test_registry_metadata_lifecycle_is_copy_on_write(catalog) -> None:
    _, _, memory, registry, _ = catalog
    skill_id = next(iter(registry.records))
    original = registry.records[skill_id]
    with pytest.raises(TypeError):
        registry.records["forbidden"] = original
    added = registry.update_skill_metadata(
        skill_id, aliases_ru=(*original.aliases_ru, "безопасный псевдоним")
    )
    assert added.manifest.registry_hash != registry.manifest.registry_hash
    assert added.manifest.registry_version == registry.manifest.registry_version + 1
    added.validate_against_rule_memory(memory)
    removed = added.update_skill_metadata(skill_id, aliases_ru=original.aliases_ru)
    removed.validate_against_rule_memory(memory)
    assert registry.records[skill_id].aliases_ru == original.aliases_ru


def test_registry_rejects_orphan_semantic_duplicate_and_strict_nested_types(
    catalog, tmp_path: Path
) -> None:
    _, _, memory, registry, _ = catalog
    records = dict(registry.records)
    first_id, second_id = list(records)[:2]
    records[first_id] = replace(records[first_id], rule_id="rule-does-not-exist")
    orphan = SkillRegistry(records, registry.manifest)
    with pytest.raises(SkillRegistryStaleError, match="orphan"):
        orphan.validate_against_rule_memory(memory)
    records = dict(registry.records)
    records[second_id] = replace(
        records[second_id], rule_semantic_hash=records[first_id].rule_semantic_hash
    )
    duplicate = SkillRegistry(records, registry.manifest)
    with pytest.raises(SkillRegistryStaleError, match="duplicate active semantic"):
        duplicate.validate_against_rule_memory(memory)

    path = tmp_path / "strict.json"
    registry.save(path)
    row = json.loads(path.read_text(encoding="utf-8"))
    row["records"][0]["rule_version"] = True
    body = {key: value for key, value in row.items() if key != "content_sha256"}
    row["content_sha256"] = content_hash(body)
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(SkillRegistryIntegrityError, match="rule_version"):
        SkillRegistry.load(path)


def test_selection_confirmation_dispatch_and_receipt_bindings(catalog) -> None:
    _, installed, _, registry, _ = catalog
    router = _router(catalog, "dispatch")
    specification = build_family_specification(
        SemanticFamily.DRAIN, sources=("A",), destination="B"
    )
    query, result = router.search_structured(specification)
    candidate = result.candidates[0]
    pending = router.prepare_selection(query, result, candidate.skill_id)
    validate_selection_receipt(pending)
    with pytest.raises(ConfirmationRequiredError):
        router.dispatch(
            query=query,
            result=result,
            selection=pending,
            proposal=installed.proposals[candidate.rule_id],
            installed_receipt=installed.receipts[candidate.rule_id],
            initial_state={"R0": 2, "R1": 3, "R2": 4, "R3": 5},
        )
    confirmed = router.confirm_selection(pending, identity="operator")
    _, execution, dispatch = router.dispatch(
        query=query,
        result=result,
        selection=confirmed,
        proposal=installed.proposals[candidate.rule_id],
        installed_receipt=installed.receipts[candidate.rule_id],
        initial_state={"R0": 2, "R1": 3, "R2": 4, "R3": 5},
    )
    assert execution.halted
    validate_dispatch_receipt(
        dispatch, initial_state={"R0": 2, "R1": 3, "R2": 4, "R3": 5}
    )
    with pytest.raises(SkillDispatchError):
        validate_dispatch_receipt(
            dispatch, initial_state={"R0": 3, "R1": 3, "R2": 4, "R3": 5}
        )
    assert registry.records[candidate.skill_id].rule_id == execution.rule_id


def test_dispatch_rejects_tampering_replay_and_unrelated_rule(catalog) -> None:
    _, installed, _, _, _ = catalog
    router = _router(catalog, "security")
    specification = build_family_specification(
        SemanticFamily.DRAIN, sources=("A",), destination="B"
    )
    query, result = router.search_structured(specification)
    candidate = result.candidates[0]
    pending = router.prepare_selection(query, result, candidate.skill_id)
    confirmed = router.confirm_selection(pending, identity="operator")
    other_rule_id = next(
        rule_id for rule_id in installed.receipts if rule_id != candidate.rule_id
    )
    with pytest.raises(SkillDispatchError):
        router.dispatch(
            query=query,
            result=result,
            selection=confirmed,
            proposal=installed.proposals[other_rule_id],
            installed_receipt=installed.receipts[other_rule_id],
            initial_state={"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    with pytest.raises(SkillDispatchError):
        validate_selection_receipt(replace(confirmed, candidate_list_hash="0" * 64))
    tampered_result = replace(
        result,
        candidates=result.candidates[::-1],
        result_hash="0" * 64,
    )
    with pytest.raises(ValueError):
        candidate_list_hash(tampered_result)
    other_query, other_result = router.search_structured(
        build_family_specification(
            SemanticFamily.DRAIN, sources=("A",), destination="C"
        )
    )
    with pytest.raises(SkillDispatchError):
        router.dispatch(
            query=other_query,
            result=other_result,
            selection=confirmed,
            proposal=installed.proposals[candidate.rule_id],
            installed_receipt=installed.receipts[candidate.rule_id],
            initial_state={"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert ConfirmationDecision.CONFIRM_SELECTION == confirmed.confirmation_decision


def test_dispatch_rejects_changed_memory_receipt_and_assistive_exact_claim(
    catalog, tmp_path: Path
) -> None:
    _, installed, memory, registry, _ = catalog
    memory_path = tmp_path / "memory.json"
    memory.save(memory_path)
    router = Stage2Router(
        registry=registry,
        memory_path=memory_path,
        stage1_audit_path=tmp_path / "stage1.jsonl",
        stage2_audit_path=tmp_path / "stage2.jsonl",
    )
    specification = build_family_specification(
        SemanticFamily.DRAIN, sources=("A",), destination="B"
    )
    query, result = router.search_structured(specification)
    candidate = result.candidates[0]
    selection = router.confirm_selection(
        router.prepare_selection(query, result, candidate.skill_id), identity="operator"
    )
    tampered_receipt = replace(
        installed.receipts[candidate.rule_id], candidate_hash="0" * 64
    )
    with pytest.raises(SkillDispatchError, match="receipt"):
        router.dispatch(
            query=query,
            result=result,
            selection=selection,
            proposal=installed.proposals[candidate.rule_id],
            installed_receipt=tampered_receipt,
            initial_state={"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    changed = RuleMemory.load(memory_path)
    changed.deprecate(candidate.rule_id)
    changed.save(memory_path)
    with pytest.raises(SkillRegistryStaleError):
        router.dispatch(
            query=query,
            result=result,
            selection=selection,
            proposal=installed.proposals[candidate.rule_id],
            installed_receipt=installed.receipts[candidate.rule_id],
            initial_state={"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )

    assistive_query, assistive = _router(catalog, "fake-exact").search_assistive(
        "Move A into B", "en"
    )
    fake = replace(assistive, exact_match=True, result_hash="0" * 64)
    with pytest.raises(ValueError):
        _router(catalog, "fake-exact-select").prepare_selection(
            assistive_query, fake, assistive.candidates[0].skill_id
        )


def test_stage2_trusted_import_does_not_import_torch() -> None:
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import ai_brain.stage2; "
                "assert 'torch' not in sys.modules; print('NO_TORCH_OK')"
            ),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "NO_TORCH_OK" in completed.stdout


def test_query_dataset_blind_isolation_and_no_model_visible_ids(
    catalog, tmp_path: Path
) -> None:
    _, _, _, registry, _ = catalog
    counts = {
        "train": 890,
        "validation": 178,
        "calibration": 178,
        "development": 356,
        "blind": 356,
    }
    manifest = generate_query_dataset(
        registry, tmp_path / "queries", seed=25001, split_counts=counts
    )
    verify_blind_freeze(tmp_path / "queries")
    assert manifest.split_counts == counts
    assert len(manifest.skill_counts) == 89
    blind = load_jsonl(tmp_path / "queries" / "blind.jsonl")
    targets = load_jsonl(tmp_path / "queries" / "blind_targets.hidden.jsonl")
    assert len(blind) == len(targets) == counts["blind"]
    assert all("target_skill_id" not in row for row in blind)
    assert all("text" not in row for row in targets)
    forbidden = set(registry.records)
    forbidden.update(item.rule_id for item in registry.records.values())
    for row in load_jsonl(tmp_path / "queries" / "train.jsonl"):
        assert not any(value in model_visible_text(row) for value in forbidden)


def test_research_biencoder_smoke_is_assistive_only(catalog, tmp_path: Path) -> None:
    import random

    from ai_brain.stage2.dataset import _generate_split
    from ai_brain.stage2.learned import (
        BiEncoderConfig,
        evaluate_retriever,
        load_retriever,
        save_retriever,
        train_bi_encoder,
    )

    _, _, _, registry, _ = catalog
    skills = sorted(registry.active_records(), key=lambda item: item.skill_id)
    used: set[str] = set()
    train = _generate_split(skills, "train", 256, rng=random.Random(1), used_text=used)
    calibration = _generate_split(
        skills, "calibration", 128, rng=random.Random(2), used_text=used
    )
    retriever, training = train_bi_encoder(
        registry,
        train,
        calibration,
        config=BiEncoderConfig(
            feature_count=256,
            hidden_size=32,
            embedding_size=16,
            batch_size=16,
            steps=2,
            seed=7,
        ),
        device="cpu",
    )
    result = retriever.rank(train[0]["text"], train[0]["language"])
    assert result["retrieval_mode"] == "LEARNED_BI_ENCODER_ASSISTIVE"
    assert not result["exact_match"]
    assert result["recommended_next_action"] in {
        "REVIEW_CANDIDATES",
        "RUN_SYNTHESIS",
    }
    assert training["steps"] == 2
    assert "top5" in evaluate_retriever(retriever, calibration)
    checkpoint = tmp_path / "retriever.pt"
    save_retriever(retriever, checkpoint, training)
    loaded = load_retriever(checkpoint)
    assert loaded.registry_hash == registry.manifest.registry_hash
