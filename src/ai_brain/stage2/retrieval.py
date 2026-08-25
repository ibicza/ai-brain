"""Trusted exact retrieval and assistive candidate-only baselines."""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, replace

from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.controlled_language import parse_controlled_language
from ai_brain.stage1.models import (
    ProposalStatus,
    content_hash,
    specification_hash,
    utc_now,
)
from ai_brain.stage1.specifications import validate_specification
from ai_brain.stage2.models import (
    NextAction,
    QuerySourceKind,
    RetrievalMode,
    SearchStatus,
    SkillCandidate,
    SkillQuery,
    SkillSearchResult,
)
from ai_brain.stage2.registry import SkillRegistry, SkillRegistryStaleError
from ai_brain.stage2.semantics import build_equivalence_groups, semantic_effect_hash

_TOKENS = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def create_query(
    source_kind: QuerySourceKind,
    original_input: str,
    *,
    language: str | None = None,
    specification: ProgramSpecification | None = None,
    required_capabilities: Iterable[str] = (),
    forbidden_effects: Iterable[str] = (),
    state_schema: Iterable[str] = (),
    query_id_factory=None,
) -> SkillQuery:
    if not isinstance(original_input, str) or not original_input.strip():
        raise ValueError("Skill query input is required")
    factory = query_id_factory or (lambda: f"query-{uuid.uuid4().hex}")
    query_id = factory()
    if not isinstance(query_id, str) or not query_id.strip():
        raise ValueError("query ID factory returned an invalid ID")
    return SkillQuery(
        query_id=query_id,
        source_kind=QuerySourceKind(source_kind),
        original_input=original_input,
        original_input_hash=content_hash(original_input),
        language=language,
        specification=specification,
        required_capabilities=tuple(required_capabilities),
        forbidden_effects=tuple(forbidden_effects),
        state_schema=tuple(state_schema),
        created_at=utc_now(),
    )


def structured_query(
    specification: ProgramSpecification, *, query_id_factory=None
) -> SkillQuery:
    return create_query(
        QuerySourceKind.STRUCTURED_SPEC,
        specification.to_model_text(),
        specification=specification,
        query_id_factory=query_id_factory,
    )


def controlled_query(text: str, language: str, *, query_id_factory=None) -> SkillQuery:
    return create_query(
        QuerySourceKind.CONTROLLED_LANGUAGE,
        text,
        language=language,
        query_id_factory=query_id_factory,
    )


def assistive_query(
    text: str, language: str | None = None, *, query_id_factory=None
) -> SkillQuery:
    return create_query(
        QuerySourceKind.ASSISTIVE_TEXT,
        text,
        language=language,
        query_id_factory=query_id_factory,
    )


def retrieve_structured(
    query: SkillQuery,
    registry: SkillRegistry,
    memory: RuleMemory,
    *,
    mode: RetrievalMode = RetrievalMode.EXACT_SPECIFICATION,
) -> SkillSearchResult:
    if query.source_kind not in {
        QuerySourceKind.STRUCTURED_SPEC,
        QuerySourceKind.CONTROLLED_LANGUAGE,
    }:
        raise ValueError("Structured retrieval requires exact evidence")
    if query.specification is None:
        raise ValueError("Structured retrieval requires ProgramSpecification")
    problems = validate_specification(query.specification)
    if problems:
        return _result(
            query,
            registry,
            memory,
            mode,
            SearchStatus.UNSUPPORTED,
            (),
            next_action=NextAction.UNSUPPORTED,
            novel=True,
        )
    try:
        registry.validate_against_rule_memory(memory)
    except SkillRegistryStaleError:
        return _result(
            query,
            registry,
            memory,
            mode,
            SearchStatus.STALE_REGISTRY,
            (),
            next_action=NextAction.UNSUPPORTED,
        )
    expected = specification_hash(query.specification)
    matches = [
        item
        for item in registry.active_records()
        if item.specification_hash == expected
    ]
    if not matches:
        return _result(
            query,
            registry,
            memory,
            mode,
            SearchStatus.NO_MATCH,
            (),
            next_action=NextAction.RUN_SYNTHESIS,
            novel=True,
        )
    if len(matches) != 1:
        return _result(
            query,
            registry,
            memory,
            mode,
            SearchStatus.AMBIGUOUS_VERSION,
            tuple(
                _candidate(item, 1.0, index + 1, "exact_hash")
                for index, item in enumerate(matches)
            ),
            next_action=NextAction.ASK_CLARIFICATION,
            ambiguous=True,
            clarification_target="rule_version",
        )
    candidate = _candidate(matches[0], 1.0, 1, "exact_specification_hash")
    return _result(
        query,
        registry,
        memory,
        mode,
        SearchStatus.EXACT_MATCH,
        (candidate,),
        next_action=NextAction.SELECT_EXACT,
        exact=True,
    )


def retrieve_semantic_signature(
    query: SkillQuery, registry: SkillRegistry, memory: RuleMemory
) -> SkillSearchResult:
    """Retrieve one proven effect class and its deterministic representative."""
    if query.source_kind != QuerySourceKind.STRUCTURED_SPEC:
        raise ValueError("Semantic retrieval requires a structured query")
    if query.specification is None:
        raise ValueError("Semantic retrieval requires ProgramSpecification")
    if validate_specification(query.specification):
        return _result(
            query,
            registry,
            memory,
            RetrievalMode.EXACT_SEMANTIC,
            SearchStatus.UNSUPPORTED,
            (),
            next_action=NextAction.UNSUPPORTED,
            novel=True,
        )
    try:
        registry.validate_against_rule_memory(memory)
    except SkillRegistryStaleError:
        return _result(
            query,
            registry,
            memory,
            RetrievalMode.EXACT_SEMANTIC,
            SearchStatus.STALE_REGISTRY,
            (),
            next_action=NextAction.UNSUPPORTED,
        )
    effect_hash = semantic_effect_hash(query.specification)
    groups = [
        item
        for item in build_equivalence_groups(registry.active_records())
        if item.semantic_effect_hash == effect_hash
    ]
    if not groups:
        return _result(
            query,
            registry,
            memory,
            RetrievalMode.EXACT_SEMANTIC,
            SearchStatus.NO_MATCH,
            (),
            next_action=NextAction.RUN_SYNTHESIS,
            novel=True,
        )
    if len(groups) != 1:
        return _result(
            query,
            registry,
            memory,
            RetrievalMode.EXACT_SEMANTIC,
            SearchStatus.AMBIGUOUS_VERSION,
            (),
            next_action=NextAction.ASK_CLARIFICATION,
            ambiguous=True,
            clarification_target="rule_version",
        )
    group = groups[0]
    canonical = registry.records[group.canonical_skill_id]
    structural_hash = specification_hash(query.specification)
    structural_members = tuple(
        item.skill_id
        for item in registry.active_records()
        if item.specification_hash == structural_hash
    )
    candidate = replace(
        _candidate(canonical, 1.0, 1, "semantic_effect_class"),
        evidence={
            "type": "semantic_effect_class",
            "semantic_effect_hash": group.semantic_effect_hash,
            "canonical_skill_id": group.canonical_skill_id,
            "member_skill_ids": list(group.member_skill_ids),
            "member_count": group.member_count,
            "equivalence_proof_kind": group.equivalence_proof_kind,
            "order_sensitive": group.order_sensitive,
            "structural_match_skill_ids": list(structural_members),
            "structural_identity_differs": canonical.skill_id not in structural_members,
        },
    )
    return _result(
        query,
        registry,
        memory,
        RetrievalMode.EXACT_SEMANTIC,
        SearchStatus.EXACT_MATCH,
        (candidate,),
        next_action=NextAction.SELECT_EXACT,
        exact=True,
    )


def retrieve_controlled(
    query: SkillQuery, registry: SkillRegistry, memory: RuleMemory
) -> SkillSearchResult:
    if query.source_kind != QuerySourceKind.CONTROLLED_LANGUAGE:
        raise ValueError("Controlled retrieval requires controlled-language query")
    if _unsupported_controlled_input(query.original_input, query.language):
        return _result(
            query,
            registry,
            memory,
            RetrievalMode.CONTROLLED_EXACT,
            SearchStatus.UNSUPPORTED,
            (),
            next_action=NextAction.UNSUPPORTED,
            novel=True,
        )
    try:
        parsed = parse_controlled_language(query.original_input, query.language)
    except ValueError:
        return _result(
            query,
            registry,
            memory,
            RetrievalMode.CONTROLLED_EXACT,
            SearchStatus.UNSUPPORTED,
            (),
            next_action=NextAction.UNSUPPORTED,
            novel=True,
        )
    if parsed.status == ProposalStatus.SUPPORTED_FOR_REVIEW and parsed.specification:
        enriched = replace(query, specification=parsed.specification)
        result = retrieve_structured(
            enriched,
            registry,
            memory,
            mode=RetrievalMode.CONTROLLED_EXACT,
        )
        # The parsed specification is trusted retrieval evidence, but selection
        # and dispatch must remain bound to the original user query artifact.
        result = replace(
            result,
            query_hash=content_hash(query),
            result_hash="0" * 64,
        )
        return replace(result, result_hash=_result_content_hash(result))
    status_map = {
        ProposalStatus.CLARIFICATION_REQUIRED: SearchStatus.AMBIGUOUS,
        ProposalStatus.CONTRADICTORY: SearchStatus.CONTRADICTORY,
        ProposalStatus.UNSUPPORTED: SearchStatus.UNSUPPORTED,
    }
    status = status_map.get(parsed.status, SearchStatus.NO_MATCH)
    target = parsed.issues[0].field if parsed.issues else None
    return _result(
        query,
        registry,
        memory,
        RetrievalMode.CONTROLLED_EXACT,
        status,
        (),
        next_action=(
            NextAction.ASK_CLARIFICATION
            if status == SearchStatus.AMBIGUOUS
            else NextAction.UNSUPPORTED
        ),
        ambiguous=status == SearchStatus.AMBIGUOUS,
        novel=status in {SearchStatus.NO_MATCH, SearchStatus.UNSUPPORTED},
        clarification_target=target,
    )


def _unsupported_controlled_input(text: str, language: str | None) -> bool:
    """Apply Stage-2 request-domain guards before the frozen Stage-1 parser."""
    if language not in {None, "ru", "en"}:
        return True
    folded = text.casefold()
    unsupported_operations = (
        "copy",
        "duplicate",
        "swap",
        "sort",
        "multiply",
        "divide",
        "compare",
        "скопируй",
        "дублируй",
        "поменяй местами",
        "отсортируй",
        "умножь",
        "раздели",
        "сравни",
    )
    return (
        any(operation in folded for operation in unsupported_operations)
        or re.search(r"\bE\b", text, re.IGNORECASE) is not None
        or re.search(r"(?<!\w)-\d+", text) is not None
    )


def retrieve_assistive(
    query: SkillQuery,
    registry: SkillRegistry,
    memory: RuleMemory,
    *,
    mode: RetrievalMode = RetrievalMode.BM25,
    top_k: int = 5,
) -> SkillSearchResult:
    if query.source_kind != QuerySourceKind.ASSISTIVE_TEXT:
        raise ValueError("Assistive retrieval requires free-text query")
    if mode not in {
        RetrievalMode.LEXICAL,
        RetrievalMode.CHARACTER_NGRAM,
        RetrievalMode.BM25,
    }:
        raise ValueError("Unsupported deterministic assistive mode")
    try:
        registry.validate_against_rule_memory(memory)
    except SkillRegistryStaleError:
        return _result(
            query,
            registry,
            memory,
            mode,
            SearchStatus.STALE_REGISTRY,
            (),
            next_action=NextAction.UNSUPPORTED,
        )
    query_terms = _tokenize(query.original_input)
    documents = {
        item.skill_id: _document(item, query.language)
        for item in registry.active_records()
    }
    scores = _scores(query.original_input, query_terms, documents, mode)
    ranked = sorted(
        registry.active_records(),
        key=lambda item: (-scores[item.skill_id], item.skill_id),
    )[:top_k]
    candidates = tuple(
        _candidate(item, scores[item.skill_id], rank, str(mode))
        for rank, item in enumerate(ranked, 1)
        if scores[item.skill_id] > 0
    )
    unsupported = _looks_unsupported(query.original_input)
    ambiguous = _looks_ambiguous(query.original_input)
    if unsupported or not candidates:
        status = SearchStatus.NO_MATCH
        action = NextAction.RUN_SYNTHESIS
    elif ambiguous:
        status = SearchStatus.AMBIGUOUS
        action = NextAction.ASK_CLARIFICATION
    else:
        status = SearchStatus.CANDIDATES
        action = NextAction.REVIEW_CANDIDATES
    return _result(
        query,
        registry,
        memory,
        mode,
        status,
        candidates,
        next_action=action,
        ambiguous=ambiguous,
        novel=unsupported or not candidates,
        clarification_target=("destination" if ambiguous else None),
    )


def validate_search_result(result: SkillSearchResult) -> None:
    expected = _result_content_hash(result)
    if result.result_hash != expected:
        raise ValueError("SkillSearchResult hash mismatch")
    if result.exact_match and result.retrieval_mode not in {
        RetrievalMode.EXACT_SPECIFICATION,
        RetrievalMode.EXACT_SEMANTIC,
        RetrievalMode.CONTROLLED_EXACT,
    }:
        raise ValueError("Assistive retrieval cannot mark a result exact")


def candidate_list_hash(result: SkillSearchResult) -> str:
    validate_search_result(result)
    return content_hash([asdict(item) for item in result.candidates])


def _result(
    query: SkillQuery,
    registry: SkillRegistry,
    memory: RuleMemory,
    mode: RetrievalMode,
    status: SearchStatus,
    candidates: tuple[SkillCandidate, ...],
    *,
    next_action: NextAction,
    exact: bool = False,
    ambiguous: bool = False,
    novel: bool = False,
    clarification_target: str | None = None,
) -> SkillSearchResult:
    result = SkillSearchResult(
        query_id=query.query_id,
        query_hash=content_hash(query),
        registry_version=registry.manifest.registry_version,
        registry_hash=registry.manifest.registry_hash,
        rule_memory_hash=registry.manifest.rule_memory_hash,
        retrieval_mode=mode,
        status=status,
        candidates=tuple(candidates),
        exact_match=exact,
        ambiguous=ambiguous,
        novel=novel,
        clarification_target=clarification_target,
        clarification_question=_clarification_question(
            clarification_target, query.language
        ),
        recommended_next_action=next_action,
        created_at=utc_now(),
        result_hash="0" * 64,
    )
    return replace(result, result_hash=_result_content_hash(result))


def _result_content_hash(result: SkillSearchResult) -> str:
    row = asdict(result)
    row["result_hash"] = "0" * 64
    return content_hash(row)


def _candidate(skill, score: float, rank: int, evidence_type: str) -> SkillCandidate:
    return SkillCandidate(
        skill_id=skill.skill_id,
        rule_id=skill.rule_id,
        rule_semantic_hash=skill.rule_semantic_hash,
        specification_hash=skill.specification_hash,
        score=round(float(score), 8),
        rank=rank,
        evidence={
            "type": evidence_type,
            "semantic_family": skill.semantic_family,
            "effect_summary": skill.effect_summary,
        },
    )


def _clarification_question(target: str | None, language: str | None) -> str | None:
    if target is None:
        return None
    questions = {
        "en": {
            "destination": "Which destination register should receive the values?",
            "source": "Which source register should be used?",
            "preserve": "Which registers must remain unchanged?",
            "phase_constraints": "Which phase must happen first?",
            "reference": "Which register does the reference denote?",
            "terminate_when_empty": "Which sources must be empty before stopping?",
            "rule_version": "Which active rule version should be selected?",
        },
        "ru": {
            "destination": "Какой регистр должен быть приёмником?",
            "source": "Какой регистр должен быть источником?",
            "preserve": "Какие регистры должны остаться без изменений?",
            "phase_constraints": "Какая фаза должна выполняться первой?",
            "reference": "Какой регистр обозначает это указание?",
            "terminate_when_empty": "Какие источники должны опустеть перед остановкой?",
            "rule_version": "Какую активную версию правила следует выбрать?",
        },
    }
    language_questions = questions["ru" if language == "ru" else "en"]
    return language_questions.get(target, f"Clarify the {target} field.")


def _document(skill, language: str | None) -> str:
    if language == "ru":
        rows = (
            skill.canonical_name_ru,
            *skill.aliases_ru,
            *skill.controlled_examples_ru,
        )
    elif language == "en":
        rows = (
            skill.canonical_name_en,
            *skill.aliases_en,
            *skill.controlled_examples_en,
        )
    else:
        rows = (
            skill.canonical_name_ru,
            skill.canonical_name_en,
            *skill.aliases_ru,
            *skill.aliases_en,
            *skill.controlled_examples_ru,
            *skill.controlled_examples_en,
        )
    return " ".join((*rows, skill.effect_summary))


def _tokenize(text: str) -> list[str]:
    return [item.casefold() for item in _TOKENS.findall(text)]


def _scores(
    query: str,
    query_terms: list[str],
    documents: dict[str, str],
    mode: RetrievalMode,
) -> dict[str, float]:
    if mode == RetrievalMode.CHARACTER_NGRAM:
        query_grams = _ngrams(query.casefold())
        return {
            key: _jaccard(query_grams, _ngrams(value.casefold()))
            for key, value in documents.items()
        }
    tokenized = {key: _tokenize(value) for key, value in documents.items()}
    if mode == RetrievalMode.LEXICAL:
        query_set = set(query_terms)
        return {
            key: _jaccard(query_set, set(value)) for key, value in tokenized.items()
        }
    document_frequency = Counter(
        token for values in tokenized.values() for token in set(values)
    )
    average_length = sum(map(len, tokenized.values())) / max(len(tokenized), 1)
    result: dict[str, float] = {}
    for key, values in tokenized.items():
        frequencies = Counter(values)
        score = 0.0
        for token in query_terms:
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse = math.log(
                1
                + (len(tokenized) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.5 * (
                0.25 + 0.75 * len(values) / max(average_length, 1)
            )
            score += inverse * frequency * 2.5 / denominator
        result[key] = score
    return result


def _ngrams(text: str, size: int = 3) -> set[str]:
    compact = " ".join(text.split())
    return {compact[index : index + size] for index in range(max(len(compact) - 2, 1))}


def _jaccard(first: set[str], second: set[str]) -> float:
    return len(first & second) / max(len(first | second), 1)


def _looks_unsupported(text: str) -> bool:
    lowered = text.casefold()
    markers = (
        "multiply",
        "divide",
        "sort",
        "swap",
        "copy",
        "duplicate",
        "compare",
        "умнож",
        "раздел",
        "сортир",
        "поменяй местами",
        "копир",
        "сравни",
        "register e",
        "регистр e",
    )
    return any(marker in lowered for marker in markers)


def _looks_ambiguous(text: str) -> bool:
    tokens = _tokenize(text)
    registers = {token.upper() for token in tokens if token.upper() in "ABCD"}
    move = any(
        token in {"move", "transfer", "перенеси", "перемести"} for token in tokens
    )
    return move and len(registers) < 2
