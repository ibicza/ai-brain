"""Frozen 89-skill structural catalog surfaces and installation helper."""

from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage1.models import InstalledRuleReceipt, RuleProposal, SemanticFamily
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.specifications import build_family_specification


def structural_specs():
    yield SemanticFamily.NOOP, (), None
    yield from ((SemanticFamily.CLEAR, (source,), None) for source in "ABCD")
    yield from (
        (SemanticFamily.DRAIN, (source,), destination)
        for source, destination in itertools.permutations("ABCD", 2)
    )
    yield from (
        (SemanticFamily.MERGE_TWO, (first, second), destination)
        for first, second, destination in itertools.permutations("ABCD", 3)
    )
    yield from (
        (SemanticFamily.MERGE_THREE, (first, second, third), destination)
        for first, second, third, destination in itertools.permutations("ABCD", 4)
    )
    yield from (
        (SemanticFamily.DROP_THEN_TRANSFER, (first, second), destination)
        for first, second, destination in itertools.permutations("ABCD", 3)
    )


def controlled_command(
    family: SemanticFamily,
    sources: tuple[str, ...],
    destination: str | None,
    language: str,
    *,
    extended: bool = False,
) -> str:
    changed = set(sources) | ({destination} if destination else set())
    preserved = tuple(value for value in "ABCD" if value not in changed)
    if language == "en":
        if family == SemanticFamily.NOOP:
            return "Leave all registers unchanged; stop immediately."
        move, drop, stop = (
            ("convey", "purge", "conclude") if extended else ("move", "clear", "stop")
        )
        preserve = (
            (
                f"retain {', '.join(preserved)} untouched"
                if extended
                else f"leave {', '.join(preserved)} unchanged"
            )
            if preserved
            else "no register is required to remain unchanged"
        )
        if family == SemanticFamily.CLEAR:
            operation = f"{drop} every item from {sources[0]}"
        elif family == SemanticFamily.DROP_THEN_TRANSFER:
            operation = (
                f"first {drop} {sources[0]}, then {move} every item "
                f"from {sources[1]} into {destination}"
            )
        else:
            operation = (
                f"{move} every item from {' and '.join(sources)} into {destination}"
            )
        return (
            f"{operation}; {preserve}; {stop} when {' and '.join(sources)} are empty."
        )
    if family == SemanticFamily.NOOP:
        return "Оставь все регистры без изменений; сразу остановись."
    move, drop, stop = (
        ("переправь", "ликвидируй", "закончи операцию")
        if extended
        else ("перенеси", "очисти", "остановись")
    )
    preserve = (
        (
            f"сбереги {', '.join(preserved)} как есть"
            if extended
            else f"{', '.join(preserved)} не изменяй"
        )
        if preserved
        else "нет регистра, который требуется сохранить без изменений"
    )
    if family == SemanticFamily.CLEAR:
        operation = f"{drop} все элементы из {sources[0]}"
    elif family == SemanticFamily.DROP_THEN_TRANSFER:
        operation = (
            f"сначала {drop} {sources[0]}, затем {move} все элементы "
            f"из {sources[1]} в {destination}"
        )
    else:
        operation = f"{move} все элементы из {' и '.join(sources)} в {destination}"
    return f"{operation}; {preserve}; {stop}, когда {' и '.join(sources)} опустеют."


@dataclass(frozen=True)
class InstalledCatalog:
    service: Stage1Service
    proposals: dict[str, RuleProposal]
    receipts: dict[str, InstalledRuleReceipt]


def install_structural_catalog(directory: Path) -> InstalledCatalog:
    service = Stage1Service(
        memory_path=directory / "rule_memory.json",
        audit_path=directory / "stage1_audit.jsonl",
    )
    proposals: dict[str, RuleProposal] = {}
    receipts: dict[str, InstalledRuleReceipt] = {}
    for family, sources, destination in structural_specs():
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )
        proposal = service.propose_form(json.loads(json.dumps(asdict(specification))))
        proposal, _ = service.review(proposal)
        proposal, candidate = service.verify(proposal)
        proposal, review = service.review_verification(proposal, candidate)
        proposal, approval = service.approve(
            proposal,
            candidate,
            review,
            identity="m25-catalog-builder",
            identity_type="TRUSTED_SUPERVISOR",
        )
        proposal, record, receipt = service.install(
            proposal, candidate, review, approval
        )
        proposals[record.rule_id] = proposal
        receipts[record.rule_id] = receipt
    return InstalledCatalog(service, proposals, receipts)
