"""Deterministic curated-source importer using the public FactMemory workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.sources import SOURCE_FILES, load_frozen_sources
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    Cardinality,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    SourceKind,
    TemporalMode,
)
from ai_brain.stage2.facts.values import FactValue, FactValueKind

IMPORT_IDENTITY = "m28-curated-chemistry-import"


@dataclass(frozen=True)
class ChemistryImportSummary:
    identity_element_count: int
    computational_element_count: int
    entity_count: int
    predicate_count: int
    source_count: int
    evidence_count: int
    claim_count: int
    fact_memory_snapshot_hash: str


def build_chemistry_fact_memory(
    root: Path, source_dir: Path | None = None
) -> tuple[FactMemory, ChemistryImportSummary]:
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("chemistry FactMemory target must be empty")
    documents = load_frozen_sources(source_dir)
    memory = FactMemory.initialize(root)
    source_records = _add_sources(memory, documents)
    _add_predicates(memory)
    elements = documents["iupac_elements_2022.json"]["elements"]
    names = documents["ru_element_names_policy_v1.json"]["names"]
    weights = documents["ciaaw_atomic_weights_2024.json"]["weights"]
    by_weight = {row["symbol"]: row for row in weights}
    evidence_count = 0
    claim_count = 0
    for index, element in enumerate(elements):
        symbol = element["symbol"]
        memory.add_entity(
            entity_id=f"element.{symbol}",
            entity_type="chemical_element",
            canonical_label_ru=names[symbol],
            canonical_label_en=element["name_en"],
            aliases_ru=(symbol,),
            aliases_en=(symbol,),
            external_identifiers={
                "atomic_number": str(element["atomic_number"]),
                "symbol": symbol,
            },
            provenance=(
                {"source_id": source_records["iupac_elements_2022.json"].source_id},
            ),
        )
        iupac_evidence = _evidence(
            memory,
            source_records["iupac_elements_2022.json"].source_id,
            f"/elements/{index}",
            f"ev_iupac_{symbol}",
        )
        ru_evidence = _evidence(
            memory,
            source_records["ru_element_names_policy_v1.json"].source_id,
            f"/names/{symbol}",
            f"ev_ru_{symbol}",
        )
        evidence_count += 2
        identity_values = (
            (
                "element_symbol",
                FactValue.create("STRING", symbol),
                iupac_evidence.evidence_id,
                source_records["iupac_elements_2022.json"].source_id,
            ),
            (
                "element_name_en",
                FactValue.create("STRING", element["name_en"]),
                iupac_evidence.evidence_id,
                source_records["iupac_elements_2022.json"].source_id,
            ),
            (
                "element_name_ru",
                FactValue.create("STRING", names[symbol]),
                ru_evidence.evidence_id,
                source_records["ru_element_names_policy_v1.json"].source_id,
            ),
            (
                "atomic_number",
                FactValue.create("INTEGER", element["atomic_number"]),
                iupac_evidence.evidence_id,
                source_records["iupac_elements_2022.json"].source_id,
            ),
            (
                "period",
                FactValue.create("INTEGER", element["period"]),
                iupac_evidence.evidence_id,
                source_records["iupac_elements_2022.json"].source_id,
            ),
            (
                "group",
                FactValue.create("INTEGER", element["group"]),
                iupac_evidence.evidence_id,
                source_records["iupac_elements_2022.json"].source_id,
            ),
        )
        for predicate, value, evidence_id, source_id in identity_values:
            _commit(memory, symbol, predicate, value, source_id, evidence_id)
            claim_count += 1
        weight = by_weight[symbol]
        weight_index = weights.index(weight)
        weight_evidence = _evidence(
            memory,
            source_records["ciaaw_atomic_weights_2024.json"].source_id,
            f"/weights/{weight_index}",
            f"ev_weight_{symbol}",
        )
        evidence_count += 1
        weight_values = [
            ("atomic_weight_kind", FactValue.create("ENUM", weight["standard_kind"])),
            (
                "conventional_atomic_weight",
                FactValue.create("DECIMAL", weight["conventional"]),
            ),
        ]
        if "value" in weight:
            weight_values.append(
                ("standard_atomic_weight", FactValue.create("DECIMAL", weight["value"]))
            )
        else:
            weight_values.extend(
                (
                    (
                        "standard_atomic_weight_lower",
                        FactValue.create("DECIMAL", weight["lower"]),
                    ),
                    (
                        "standard_atomic_weight_upper",
                        FactValue.create("DECIMAL", weight["upper"]),
                    ),
                )
            )
        for predicate, value in weight_values:
            _commit(
                memory,
                symbol,
                predicate,
                value,
                source_records["ciaaw_atomic_weights_2024.json"].source_id,
                weight_evidence.evidence_id,
            )
            claim_count += 1
    bipm = documents["bipm_si_mole_2026.json"]
    memory.add_entity(
        entity_id="constant.avogadro",
        entity_type="chemistry_constant",
        canonical_label_ru="постоянная Авогадро",
        canonical_label_en="Avogadro constant",
        aliases_ru=("N_A",),
        aliases_en=("N_A",),
        provenance=({"source_id": source_records["bipm_si_mole_2026.json"].source_id},),
    )
    avogadro_evidence = _evidence(
        memory,
        source_records["bipm_si_mole_2026.json"].source_id,
        "/mole/avogadro_constant",
        "ev_avogadro",
    )
    evidence_count += 1
    _commit(
        memory,
        "avogadro",
        "avogadro_constant",
        FactValue.create("QUANTITY", bipm["mole"]["avogadro_constant"], unit="mol^-1"),
        source_records["bipm_si_mole_2026.json"].source_id,
        avogadro_evidence.evidence_id,
        subject="constant.avogadro",
    )
    claim_count += 1
    memory.verify()
    summary = ChemistryImportSummary(
        identity_element_count=len(elements),
        computational_element_count=len(weights),
        entity_count=len(elements) + 1,
        predicate_count=12,
        source_count=len(source_records),
        evidence_count=evidence_count,
        claim_count=claim_count,
        fact_memory_snapshot_hash=memory.database.snapshot_hash(),
    )
    return memory, summary


def _add_sources(
    memory: FactMemory, documents: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    records = {}
    for name in SOURCE_FILES:
        document = dict(documents[name])
        document.pop("_integrity")
        metadata = document["source"]
        official = name != "ru_element_names_policy_v1.json"
        records[name] = memory.add_source(
            content=document,
            source_kind=SourceKind.OFFICIAL_PRIMARY
            if official
            else SourceKind.LOCAL_DOCUMENT,
            title=metadata["title"],
            author=metadata["authority"],
            publisher=metadata["authority"],
            locator=metadata.get("url")
            or metadata.get("standard_url")
            or metadata.get("locator"),
            published_at=metadata["published_at"],
            retrieved_at=metadata["retrieved_at"],
            language=metadata["language"],
            source_family=metadata["source_family"],
            trust_tier="AUTHORITATIVE_PRIMARY"
            if official
            else "REVIEWED_DOMAIN_POLICY",
            license_metadata={
                "license": metadata.get("license", "unknown"),
                "limitations": metadata.get("limitations", ""),
            },
            original_filename=name,
            media_type="application/json",
            source_id=f"source_{name.removesuffix('.json')}",
        )
    return records


def _add_predicates(memory: FactMemory) -> None:
    definitions = (
        (
            "element_symbol",
            "символ элемента",
            "element symbol",
            "chemical_element",
            "STRING",
        ),
        (
            "element_name_ru",
            "название элемента по-русски",
            "Russian element name",
            "chemical_element",
            "STRING",
        ),
        (
            "element_name_en",
            "название элемента по-английски",
            "English element name",
            "chemical_element",
            "STRING",
        ),
        (
            "atomic_number",
            "атомный номер",
            "atomic number",
            "chemical_element",
            "INTEGER",
        ),
        ("period", "период", "period", "chemical_element", "INTEGER"),
        ("group", "группа", "group", "chemical_element", "INTEGER"),
        (
            "atomic_weight_kind",
            "вид стандартной атомной массы",
            "atomic-weight kind",
            "chemical_element",
            "ENUM",
        ),
        (
            "standard_atomic_weight",
            "стандартная атомная масса",
            "standard atomic weight",
            "chemical_element",
            "DECIMAL",
        ),
        (
            "standard_atomic_weight_lower",
            "нижняя граница атомной массы",
            "atomic-weight lower bound",
            "chemical_element",
            "DECIMAL",
        ),
        (
            "standard_atomic_weight_upper",
            "верхняя граница атомной массы",
            "atomic-weight upper bound",
            "chemical_element",
            "DECIMAL",
        ),
        (
            "conventional_atomic_weight",
            "условная учебная атомная масса",
            "conventional classroom atomic weight",
            "chemical_element",
            "DECIMAL",
        ),
        (
            "avogadro_constant",
            "постоянная Авогадро",
            "Avogadro constant",
            "chemistry_constant",
            "QUANTITY",
        ),
    )
    for predicate_id, ru, en, subject_type, kind in definitions:
        memory.add_predicate(
            predicate_id=predicate_id,
            canonical_name_ru=ru,
            canonical_name_en=en,
            subject_entity_type=subject_type,
            object_kind=FactValueKind(kind),
            cardinality=Cardinality.SINGLE,
            temporal_mode=TemporalMode.ATEMPORAL,
            unit_dimension="amount^-1" if predicate_id == "avogadro_constant" else None,
        )


def _evidence(memory: FactMemory, source_id: str, pointer: str, evidence_id: str):
    return memory.add_evidence(
        source_id=source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.JSON_POINTER,
        location={"pointer": pointer},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence="1",
        reviewer=IMPORT_IDENTITY,
        reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
        approved=True,
        evidence_id=evidence_id,
    )


def _commit(
    memory: FactMemory,
    symbol: str,
    predicate: str,
    value: FactValue,
    source_id: str,
    evidence_id: str,
    *,
    subject: str | None = None,
) -> None:
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id=subject or f"element.{symbol}",
        predicate_id=predicate,
        object_value=value,
        source_ids=(source_id,),
        evidence_ids=(evidence_id,),
        proposal_id=f"proposal_{symbol}_{predicate}",
    )
    memory.prepare_for_review(
        proposal.proposal_id,
        reviewer=IMPORT_IDENTITY,
        reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
    )
    approval = memory.approve_proposal(
        proposal.proposal_id,
        reviewer_identity=IMPORT_IDENTITY,
        reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
    )
    memory.commit_proposal(proposal.proposal_id, approval.approval_id)


def write_import_summary(summary: ChemistryImportSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.__dict__, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
