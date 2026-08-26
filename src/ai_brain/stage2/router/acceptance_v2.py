"""Deterministic M-27.1 hardening acceptance battery."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.acceptance_v2 import run_m261_acceptance
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.migration import (
    create_v3_compatibility_fixture,
    migrate_v3_to_v4,
)
from ai_brain.stage2.router.exact import ExactUnifiedRouter
from ai_brain.stage2.router.models import (
    DependencySnapshot,
    ReplayStatus,
    RequestSourceKind,
    ResponseStage,
    RouteStatus,
)
from ai_brain.stage2.router.persistence import (
    RouterStore,
    create_router_v1_compatibility_fixture,
    migrate_router_store_v1_to_v2,
)
from ai_brain.stage2.router.request import create_request
from ai_brain.stage2.router.service import UnifiedRouterService
from ai_brain.stage2.router.tool_registry import (
    ToolRegistry,
    build_tool_implementation_manifest,
)
from ai_brain.stage2.router.tools import ToolInputError, decimal_arithmetic


def run_m271_acceptance(output_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    output = output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("M-27.1 acceptance output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    replay_checks = 0
    decimal_rejections = 0
    manifest_checks = 0
    with tempfile.TemporaryDirectory(prefix="ai-brain-m271-") as temporary:
        root = Path(temporary)
        store = RouterStore.initialize(root / "router")
        service = UnifiedRouterService(
            ExactUnifiedRouter(tool_registry=ToolRegistry.default()), store=store
        )
        request = create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 12.5 plus 3.",
            language="en",
        )
        _, prepared = service.handle(request)
        require(prepared.response_stage == ResponseStage.PREPARED, "tool not prepared")
        require(
            service.replay(prepared).overall_status == ReplayStatus.CURRENT,
            "current replay failed",
        )
        current = service.router.dependencies()
        replay_cases = (
            ("fact_memory_hash", "1" * 64, ReplayStatus.STALE_FACT_MEMORY),
            ("skill_registry_hash", "2" * 64, ReplayStatus.STALE_SKILL_REGISTRY),
            ("rule_memory_hash", "3" * 64, ReplayStatus.STALE_RULE_MEMORY),
            ("tool_registry_hash", "4" * 64, ReplayStatus.STALE_TOOL_REGISTRY),
            (
                "tool_implementation_manifest_hashes",
                (("decimal_arithmetic", "5" * 64),),
                ReplayStatus.STALE_TOOL_IMPLEMENTATION,
            ),
            ("stage1_version", "0", ReplayStatus.INCOMPATIBLE_VERSION),
            ("tool_policy_version", "0", ReplayStatus.INCOMPATIBLE_VERSION),
            ("equivalence_policy_version", "0", ReplayStatus.INCOMPATIBLE_VERSION),
        )
        for field_name, value, expected in replay_cases:
            stored = _changed_snapshot(current, field_name, value)
            response = _rehash_response(prepared, stored)
            report = service.replay(response)
            require(report.overall_status == expected, f"replay missed {field_name}")
            require(
                field_name in {*report.stale_components, *report.incompatible_versions},
                f"replay did not name {field_name}",
            )
            replay_checks += 1

        baseline = build_tool_implementation_manifest("decimal_arithmetic")
        manifest_mutations = (
            ({"decimal_arithmetic": "changed"}, {}),
            ({"_decimal": "changed"}, {}),
            ({"_render_decimal": "changed"}, {}),
            ({}, {"MAX_OPERANDS": 15}),
            ({}, {"DECIMAL_TOOL_LIMITS": {"max_absolute_exponent": 1}}),
            ({}, {"DECIMAL_CONTEXT_POLICY": "changed"}),
            ({}, {"DECIMAL_RENDERING_POLICY": "changed"}),
        )
        for sources, constants in manifest_mutations:
            changed = build_tool_implementation_manifest(
                "decimal_arithmetic",
                source_overrides=sources,
                constant_overrides=constants,
            )
            require(
                changed.manifest_hash != baseline.manifest_hash, "manifest collision"
            )
            manifest_checks += 1

        attacks: tuple[Any, ...] = (
            "1e999999",
            "1e-999999",
            "9" * 1000,
            1 << 100_000,
            True,
            1.5,
            b"1",
            [],
            {},
            "NaN",
            "Infinity",
            "sNaN",
        )
        for attack in attacks:
            try:
                decimal_arithmetic({"operation": "ADD", "operands": [attack, "1"]})
            except ToolInputError:
                decimal_rejections += 1
            else:
                require(False, "Decimal attack was accepted")
        require(decimal_rejections == len(attacks), "Decimal attack count mismatch")
        try:
            decimal_arithmetic({"operation": "ADD", "operands": ["1"] * 17})
        except ToolInputError:
            decimal_rejections += 1
        else:
            require(False, "17 operands were accepted")
        try:
            decimal_arithmetic({"operation": "DIVIDE", "operands": ["1", "0"]})
        except ToolInputError:
            decimal_rejections += 1
        else:
            require(False, "division by zero was accepted")

        invalid_request = create_request(
            RequestSourceKind.STRUCTURED_TOOL,
            structured_payload={
                "tool_id": "decimal_arithmetic",
                "arguments": {"operation": "DIVIDE", "operands": ["1", "0"]},
            },
        )
        invalid_decision, invalid_response = service.handle(invalid_request)
        require(
            invalid_decision.route_status == RouteStatus.INVALID_REQUEST,
            "invalid tool received exact route",
        )
        require(invalid_response.tool_proposal_hash is None, "invalid proposal created")

        proposal = service._tool_proposals[prepared.tool_proposal_hash]
        confirmation = service.confirm_tool(proposal, identity="m271-acceptance")
        result, completed = service.execute_tool_and_respond(
            prepared, proposal, confirmation
        )
        require(result is not None and result.output["result"] == "15.5", "tool failed")
        require(
            completed.response_stage == ResponseStage.COMPLETED, "tool not completed"
        )
        require(
            service.replay(completed).overall_status == ReplayStatus.CURRENT,
            "completed tool replay failed",
        )

        failed_request = create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 4 plus 5.",
            language="en",
        )
        _, failed_prepared = service.handle(failed_request)
        failed_proposal = service._tool_proposals[failed_prepared.tool_proposal_hash]
        _, failed = service.execute_tool_and_respond(
            failed_prepared, failed_proposal, None
        )
        require(failed.response_stage == ResponseStage.FAILED, "failure not finalized")
        require(failed.tool_result_hash is None, "failed response has authority")

        create_router_v1_compatibility_fixture(store.root, root / "router-v1")
        router_manifest = migrate_router_store_v1_to_v2(
            root / "router-v1", root / "router-v2"
        )
        require(router_manifest["source_unchanged"], "router source changed")
        migrated_store = RouterStore(root / "router-v2")
        require(
            migrated_store.verify()["status"] == "VALID", "router migration invalid"
        )
        with migrated_store.connect() as connection:
            legacy_hash = connection.execute(
                "SELECT artifact_hash FROM artifacts WHERE artifact_type = 'response' LIMIT 1"
            ).fetchone()[0]
        from ai_brain.stage2.router.cli import _response

        legacy = _response(migrated_store.find_hash(legacy_hash)[1])
        require(
            service.replay(legacy).overall_status
            == ReplayStatus.INCOMPATIBLE_LEGACY_ARTIFACT,
            "legacy response reported current",
        )

        facts = FactMemory.initialize(root / "facts-v4")
        create_v3_compatibility_fixture(facts.root, root / "facts-v3")
        fact_manifest = migrate_v3_to_v4(root / "facts-v3", root / "facts-out")
        require(fact_manifest["source_unchanged"], "FactMemory source changed")
        require(
            FactMemory.open(root / "facts-out").verify()["status"] == "VALID",
            "FactMemory migration invalid",
        )

        conflict_report = run_m261_acceptance(root / "m261")
        require(conflict_report["status"] == "PASS", "M-26.1 conflict regression")
        manual = next(
            item
            for item in conflict_report["cases"]
            if item["name"] == "manual_resolution"
        )
        require(manual["passed"], "strict manual resolution failed")

        torch_probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ai_brain.stage2.router; print('torch' in sys.modules)",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        require(torch_probe == "False", "trusted import loaded torch")
        store_integrity = store.verify()
        require(store_integrity["status"] == "VALID", "RouterStore v2 invalid")

    report = {
        "milestone": "M-27.1",
        "status": "PASS",
        "checks": checks,
        "dependency_replay_mutations": replay_checks,
        "tool_manifest_mutations": manifest_checks,
        "decimal_attack_rejections": decimal_rejections,
        "conflict_policy_cases": conflict_report["case_count"],
        "router_store_migration": "PASS",
        "fact_memory_migration": "PASS",
        "tool_lifecycle": "PREPARED_TO_COMPLETED_AND_FAILED",
        "trusted_import_loads_torch": False,
        "router_store": store_integrity,
        "duration_seconds": format(time.perf_counter() - started, ".6f"),
    }
    (output / "m271_acceptance.json").write_text(
        canonical_json(report) + "\n", encoding="utf-8"
    )
    return report


def _changed_snapshot(
    snapshot: DependencySnapshot, field_name: str, value: Any
) -> DependencySnapshot:
    body = asdict(snapshot)
    body.pop("dependency_snapshot_hash")
    body[field_name] = value
    return DependencySnapshot(**body, dependency_snapshot_hash=content_hash(body))


def _rehash_response(response, snapshot: DependencySnapshot):
    changed = replace(
        response,
        dependency_snapshots=asdict(snapshot),
        dependency_snapshot_hash=snapshot.dependency_snapshot_hash,
        response_hash="",
    )
    body = asdict(changed)
    body.pop("response_hash")
    return replace(changed, response_hash=content_hash(body))
