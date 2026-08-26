"""Separate SQL, full FactMemory, and unified-response latency measurement."""

from __future__ import annotations

import math
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import install_structural_catalog, structural_specs
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.registry import rebuild_from_rule_memory
from ai_brain.stage2.router import (
    ExactUnifiedRouter,
    ToolRegistry,
    UnifiedRouterService,
    create_request,
)
from ai_brain.stage2.router.models import RequestSourceKind
from ai_brain.stage2.router.persistence import RouterStore
from ai_brain.stage2.router.tool_registry import build_tool_implementation_manifest
from ai_brain.stage2.service import Stage2Router


def benchmark_fact_response(
    fact_root: Path,
    *,
    subject: str,
    predicate_id: str,
    samples: int = 200,
) -> dict[str, Any]:
    if samples < 10:
        raise ValueError("at least ten samples are required")
    memory = FactMemory.open(fact_root)
    service = UnifiedRouterService(
        ExactUnifiedRouter(tool_registry=ToolRegistry.default(), fact_memory=memory)
    )

    def sql_lookup() -> None:
        with memory.database.connect() as connection:
            connection.execute(
                "SELECT claim_id FROM claims WHERE subject_entity_id = ? AND predicate_id = ? ORDER BY recorded_at, claim_id",
                (subject, predicate_id),
            ).fetchall()

    def full_query() -> None:
        query = memory.make_query(subject=subject, predicate_id=predicate_id)
        memory.query(query)

    def unified() -> None:
        request = create_request(
            RequestSourceKind.STRUCTURED_FACT,
            structured_payload={"subject": subject, "predicate_id": predicate_id},
        )
        service.handle(request)

    return {
        "samples": samples,
        "INDEXED_SQL_LOOKUP": _measure(sql_lookup, samples),
        "END_TO_END_FACT_QUERY": _measure(full_query, samples),
        "UNIFIED_ROUTER_FACT_RESPONSE": _measure(unified, samples),
    }


def benchmark_router_hardening(*, samples: int = 30) -> dict[str, Any]:
    if samples < 10:
        raise ValueError("at least ten samples are required")
    with tempfile.TemporaryDirectory(prefix="ai-brain-m271-perf-") as temporary:
        root = Path(temporary)
        catalog = install_structural_catalog(root / "catalog")
        memory = RuleMemory.load(catalog.service.memory_path)
        registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
        skill_router = Stage2Router(
            registry=registry,
            memory_path=catalog.service.memory_path,
            stage1_audit_path=catalog.service.audit.path,
            stage2_audit_path=root / "stage2.jsonl",
        )
        store = RouterStore.initialize(root / "router")
        service = UnifiedRouterService(
            ExactUnifiedRouter(
                tool_registry=ToolRegistry.default(), skill_router=skill_router
            ),
            store=store,
        )
        request = create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 2 plus 3.",
            language="en",
        )
        _, response = service.handle(request)
        family, sources, destination = next(iter(structural_specs()))
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )

        def complete_tool() -> None:
            tool_request = create_request(
                RequestSourceKind.CONTROLLED_LANGUAGE,
                original_input="Calculate 12.5 plus 3.",
                language="en",
            )
            _, prepared = service.handle(tool_request)
            proposal = service._tool_proposals[prepared.tool_proposal_hash]
            confirmation = service.confirm_tool(proposal, identity="benchmark")
            service.execute_tool_and_respond(prepared, proposal, confirmation)

        def complete_skill() -> None:
            skill_request = create_request(
                RequestSourceKind.STRUCTURED_SKILL,
                structured_payload=asdict(specification),
            )
            decision, prepared = service.handle(skill_request)
            service.confirm_skill(decision, identity="benchmark")
            skill = registry.records[decision.parser_evidence["selected_skill_id"]]
            service.dispatch_skill_and_respond(
                prepared,
                skill_request,
                decision,
                proposal=catalog.proposals[skill.rule_id],
                installed_receipt=catalog.receipts[skill.rule_id],
                initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7},
            )

        result = {
            "samples": samples,
            "DEPENDENCY_SNAPSHOT": _measure(service.router.dependencies, samples * 3),
            "FULL_REPLAY": _measure(lambda: service.replay(response), samples * 3),
            "TOOL_IMPLEMENTATION_MANIFEST": _measure(
                lambda: build_tool_implementation_manifest("decimal_arithmetic"),
                samples * 3,
            ),
            "DECIMAL_VALIDATION": _measure(
                lambda: (
                    service.router.tool_registry.validate_and_canonicalize_arguments(
                        "decimal_arithmetic",
                        {"operation": "ADD", "operands": ["12.5", "3"]},
                    )
                ),
                samples * 3,
            ),
            "COMPLETE_TOOL_RESPONSE": _measure(complete_tool, samples),
            "COMPLETE_SKILL_RESPONSE": _measure(complete_skill, max(10, samples // 3)),
        }
        result["ROUTER_STORE_VERIFY"] = _measure(store.verify, 10)
        result["router_store"] = store.verify()
        return result


def _measure(operation: Callable[[], None], samples: int) -> dict[str, float]:
    values = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(values)
    return {
        "p50_ms": _percentile(ordered, 0.50),
        "p95_ms": _percentile(ordered, 0.95),
        "p99_ms": _percentile(ordered, 0.99),
    }


def _percentile(values: list[float], quantile: float) -> float:
    index = max(0, math.ceil(len(values) * quantile) - 1)
    return values[index]
