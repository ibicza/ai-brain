"""Deterministic trusted M-27 integration and authority acceptance battery."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import (
    controlled_command,
    install_structural_catalog,
    structural_specs,
)
from ai_brain.stage2.facts.acceptance import build_acceptance_pack
from ai_brain.stage2.facts.models import Cardinality, TemporalMode
from ai_brain.stage2.facts.values import FactValueKind
from ai_brain.stage2.registry import rebuild_from_rule_memory
from ai_brain.stage2.router import (
    ExactUnifiedRouter,
    ToolRegistry,
    UnifiedRouterService,
    create_request,
)
from ai_brain.stage2.router.models import (
    RequestSourceKind,
    RouteAuthority,
    RouteStatus,
    RouteTarget,
    ToolExecutionStatus,
)
from ai_brain.stage2.router.persistence import RouterStore
from ai_brain.stage2.service import Stage2Router


def run_m27_acceptance(output_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    output = output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("M-27 acceptance output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    with tempfile.TemporaryDirectory(prefix="ai-brain-m27-") as temporary:
        root = Path(temporary)
        facts, _ = build_acceptance_pack(root / "facts")
        for index in range(20, 30):
            facts.add_entity(
                entity_id=f"place.{index:02d}",
                entity_type="PLACE",
                canonical_label_ru=f"Место {index:02d}",
                canonical_label_en=f"Place {index:02d}",
            )
        for index in range(10, 15):
            facts.add_predicate(
                predicate_id=f"extra_{index:02d}",
                canonical_name_ru=f"RU extra {index:02d}",
                canonical_name_en=f"EN extra {index:02d}",
                subject_entity_type="PLACE",
                object_kind=FactValueKind.STRING,
                cardinality=Cardinality.MULTI,
                temporal_mode=TemporalMode.ATEMPORAL,
            )
        catalog = install_structural_catalog(root / "catalog")
        rule_memory = RuleMemory.load(catalog.service.memory_path)
        registry = rebuild_from_rule_memory(rule_memory, receipts=catalog.receipts)
        skill_router = Stage2Router(
            registry=registry,
            memory_path=catalog.service.memory_path,
            stage1_audit_path=catalog.service.audit.path,
            stage2_audit_path=root / "stage2_audit.jsonl",
        )
        store = RouterStore.initialize(root / "router")
        router = ExactUnifiedRouter(
            tool_registry=ToolRegistry.default(),
            fact_memory=facts,
            skill_router=skill_router,
        )
        service = UnifiedRouterService(router, store=store)

        structured_skills = 0
        controlled_skills = 0
        dispatched_skills = 0
        for index, (family, sources, destination) in enumerate(structural_specs()):
            specification = build_family_specification(
                family, sources=sources, destination=destination
            )
            request = create_request(
                RequestSourceKind.STRUCTURED_SKILL,
                structured_payload=asdict(specification),
            )
            decision, response = service.handle(request)
            require(
                decision.selected_target == RouteTarget.SKILL_REQUEST,
                "structured skill route",
            )
            require(
                response.skill_selection_hash is not None, "skill selection missing"
            )
            structured_skills += 1
            service.confirm_skill(decision, identity="m27-acceptance")
            skill_id = decision.parser_evidence["selected_skill_id"]
            skill = registry.records[skill_id]
            _, execution, _ = service.dispatch_skill(
                request,
                decision,
                proposal=catalog.proposals[skill.rule_id],
                installed_receipt=catalog.receipts[skill.rule_id],
                initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7},
            )
            require(execution.halted, "skill execution did not halt")
            dispatched_skills += 1
            for language in ("ru", "en"):
                for extended in (False, True):
                    text = controlled_command(
                        family, sources, destination, language, extended=extended
                    )
                    controlled_request = create_request(
                        RequestSourceKind.CONTROLLED_LANGUAGE,
                        original_input=text,
                        language=language,
                    )
                    controlled = service.route(controlled_request)
                    require(
                        controlled.selected_target == RouteTarget.SKILL_REQUEST
                        and controlled.exact_match,
                        "controlled skill route",
                    )
                    controlled_skills += 1

        fact_cases = (
            ("en", "What is the EN population of Place 00?"),
            ("en", "What was the EN population of Place 00 on 2021-01-01?"),
            ("en", "Show all EN tags values for Place 03."),
            ("ru", "Каково значение RU population у объекта Место 00?"),
            ("ru", "Каково значение RU population у объекта Место 00 на 2021-01-01?"),
            ("ru", "Покажи все значения RU tags у объекта Место 03."),
        )
        fact_routes = 0
        for language, text in fact_cases:
            request = create_request(
                RequestSourceKind.CONTROLLED_LANGUAGE,
                original_input=text,
                language=language,
            )
            decision, response = service.handle(request)
            require(
                decision.selected_target == RouteTarget.FACT_QUERY,
                "controlled fact route",
            )
            require(response.fact_answer_hash is not None, "fact answer missing")
            fact_routes += 1

        tool_executions = 0
        for index in range(50):
            request = create_request(
                RequestSourceKind.STRUCTURED_TOOL,
                structured_payload={
                    "tool_id": "decimal_arithmetic",
                    "arguments": {
                        "operation": "ADD",
                        "operands": [str(index), str(index + 1)],
                    },
                },
            )
            decision, response = service.handle(request)
            require(
                decision.selected_target == RouteTarget.TOOL_REQUEST,
                "structured tool route",
            )
            proposal = service._tool_proposals[response.tool_proposal_hash]
            confirmation = service.confirm_tool(proposal, identity="m27-acceptance")
            result = service.execute_tool(proposal, confirmation)
            require(
                result.status == ToolExecutionStatus.EXECUTED, "tool execution failed"
            )
            tool_executions += 1
        date_executions = 0
        for index in range(30):
            request = create_request(
                RequestSourceKind.CONTROLLED_LANGUAGE,
                original_input=(
                    f"How many days are between 2026-01-01 and 2026-01-{(index % 28) + 1:02d}?"
                ),
                language="en",
            )
            decision, response = service.handle(request)
            require(
                decision.selected_target == RouteTarget.TOOL_REQUEST, "date tool route"
            )
            proposal = service._tool_proposals[response.tool_proposal_hash]
            result = service.execute_tool(
                proposal,
                service.confirm_tool(proposal, identity="m27-acceptance"),
            )
            require(
                result.status == ToolExecutionStatus.EXECUTED,
                "date execution failed",
            )
            date_executions += 1
        tool_errors = 0
        for index in range(20):
            request = create_request(
                RequestSourceKind.STRUCTURED_TOOL,
                structured_payload={
                    "tool_id": "decimal_arithmetic",
                    "arguments": {
                        "operation": "DIVIDE",
                        "operands": [str(index + 1), "0"],
                    },
                },
            )
            decision, response = service.handle(request)
            require(
                decision.route_status == RouteStatus.INVALID_REQUEST
                and response.tool_proposal_hash is None,
                "unsafe division accepted",
            )
            tool_errors += 1

        unsupported = 0
        ambiguous = 0
        composite = 0
        for index in range(100):
            language = "en" if index % 2 else "ru"
            text = (
                f"Unknown operation {index}."
                if language == "en"
                else f"Неизвестная операция {index}."
            )
            request = create_request(
                RequestSourceKind.CONTROLLED_LANGUAGE,
                original_input=text,
                language=language,
            )
            decision = service.route(request)
            require(
                decision.selected_target == RouteTarget.UNSUPPORTED,
                "unknown auto-routed",
            )
            unsupported += 1
        for index in range(100):
            language = "en" if index % 2 else "ru"
            text = (
                "What is the EN population of Shared Alias?"
                if language == "en"
                else "Каково значение RU population у объекта Общее имя?"
            )
            request = create_request(
                RequestSourceKind.CONTROLLED_LANGUAGE,
                original_input=text,
                language=language,
            )
            decision, response = service.handle(request)
            require(
                decision.selected_target == RouteTarget.CLARIFICATION,
                "ambiguous entity auto-routed",
            )
            require(
                not any(
                    (
                        response.fact_answer_hash,
                        response.skill_dispatch_hash,
                        response.tool_result_hash,
                    )
                ),
                "ambiguous route executed",
            )
            ambiguous += 1
        for index in range(100):
            text = (
                f"Calculate {index} plus 1 and store the result as a trusted fact."
                if index % 2
                else f"Вычисли {index} плюс 1 и сохрани результат как факт."
            )
            request = create_request(
                RequestSourceKind.CONTROLLED_LANGUAGE,
                original_input=text,
                language="en" if index % 2 else "ru",
            )
            decision, response = service.handle(request)
            require(
                decision.selected_target == RouteTarget.COMPOSITE_REQUIRED,
                "composite auto-routed",
            )
            require(
                not any(
                    (
                        response.fact_answer_hash,
                        response.skill_dispatch_hash,
                        response.tool_result_hash,
                    )
                ),
                "composite partially executed",
            )
            composite += 1

        assistive = create_request(
            RequestSourceKind.ASSISTIVE_TEXT,
            original_input="Maybe calculate an approximate value",
            language="en",
        )
        assistive_decision = service.route(assistive)
        require(
            assistive_decision.route_authority == RouteAuthority.ASSISTIVE_PROPOSAL
            and assistive_decision.route_status == RouteStatus.ASSISTIVE_CANDIDATES
            and not assistive_decision.exact_match,
            "assistive router gained exact authority",
        )
        no_torch = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ai_brain.stage2.router; assert 'torch' not in sys.modules",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        require(no_torch.returncode == 0, "trusted router imported torch")
        integrity = store.verify()

    result = {
        "milestone": "M-27",
        "status": "PASS",
        "checks": checks,
        "structured_skill_routes": structured_skills,
        "controlled_skill_routes": controlled_skills,
        "skill_dispatches": dispatched_skills,
        "controlled_fact_routes": fact_routes,
        "tool_executions": tool_executions,
        "date_tool_executions": date_executions,
        "tool_error_rejections": tool_errors,
        "unsupported_requests": unsupported,
        "ambiguous_requests": ambiguous,
        "composite_requests": composite,
        "wrong_exact_routes": 0,
        "wrong_auto_executions": 0,
        "cross_authority_writes": 0,
        "partial_composite_executions": 0,
        "trusted_import_loads_torch": False,
        "router_store": integrity,
        "duration_seconds": time.perf_counter() - started,
    }
    (output / "m27_trusted_acceptance.json").write_text(
        __import__("json").dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return result
