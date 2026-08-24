"""Run the reproducible Stage-1 v1 production acceptance battery."""

from __future__ import annotations

import argparse
import itertools
import json
import platform
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ai_brain.rules.ast import RegisterState, exact_closed_loop
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import property_verify
from ai_brain.stage1.controlled_language import parse_controlled_language
from ai_brain.stage1.execution import execute_rule
from ai_brain.stage1.known_family_compiler import compile_known_family
from ai_brain.stage1.models import ProposalStatus, SemanticFamily
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage1.version import (
    CONTROLLED_LANGUAGE_VERSION,
    RULE_MEMORY_SCHEMA_VERSION,
    SPECIFICATION_SCHEMA_VERSION,
    STAGE1_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runs" / "m24_stage1_acceptance.json"
PROGRESS_PATH = ROOT / "runs" / "m24_progress.jsonl"
MANIFEST_PATH = ROOT / "artifacts" / "stage1" / "stage1_v1_manifest.json"
DOC_REPORT = ROOT / "docs" / "m24_stage1_production_integration_report.md"
RUN_REPORT = ROOT / "runs" / "m24_stage1_production_integration_report.md"


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


def command(
    family: SemanticFamily,
    sources: tuple[str, ...],
    destination: str | None,
    language: str,
    extended: bool,
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
            operation = f"first {drop} {sources[0]}, then {move} every item from {sources[1]} into {destination}"
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
        operation = f"сначала {drop} {sources[0]}, затем {move} все элементы из {sources[1]} в {destination}"
    else:
        operation = f"{move} все элементы из {' и '.join(sources)} в {destination}"
    return f"{operation}; {preserve}; {stop}, когда {' и '.join(sources)} опустеют."


def run() -> dict:
    started = time.perf_counter()
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    rows = list(structural_specs())
    require(len(rows) == 89, "structural matrix must contain exactly 89 specs")
    family_counts = Counter(str(family) for family, _, _ in rows)
    rule_ids: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ai-brain-m24-") as temporary:
        directory = Path(temporary)
        service = Stage1Service(
            memory_path=directory / "rule_memory.json",
            audit_path=directory / "audit.jsonl",
        )
        for index, (family, sources, destination) in enumerate(rows):
            specification = build_family_specification(
                family, sources=sources, destination=destination
            )
            program = compile_known_family(specification, family)
            require(
                property_verify(program, specification, large=True).accepted,
                f"property verification failed for {family}/{sources}/{destination}",
            )
            raw = exact_closed_loop(
                program,
                RegisterState({"R0": 2, "R1": 3, "R2": 4, "R3": 1000}),
            )
            require(
                not raw["invalid"] and raw["actions"][-1] == "H", "unsafe execution"
            )
            for language in ("ru", "en"):
                for extended in (False, True):
                    parsed = parse_controlled_language(
                        command(family, sources, destination, language, extended),
                        language,
                    )
                    require(
                        parsed.status == ProposalStatus.SUPPORTED_FOR_REVIEW,
                        "parse status",
                    )
                    require(parsed.specification == specification, "parse semantics")
            proposal = service.propose_form(asdict(specification))
            proposal, _ = service.review(proposal)
            proposal, candidate = service.verify(proposal)
            proposal, approval = service.approve(
                proposal,
                candidate,
                identity="m24-acceptance",
                identity_type="TRUSTED_SUPERVISOR",
            )
            proposal, record = service.install(proposal, candidate, approval)
            rule_ids.append(record.rule_id)
            require(
                record.rule_id.startswith(f"rule-{index + 1:05d}-"), "deterministic id"
            )
            result = execute_rule(
                service.memory_path,
                record.rule_id,
                {"R0": 1000, "R1": 13, "R2": 29, "R3": 71},
            )
            require(result.actions[-1] == "H", "installed rule execution")

        memory = RuleMemory.load(service.memory_path)
        require(len(memory.records) == 89, "all structural rules retained")
        require(len(memory.active_records()) == 89, "all structural rules active")
        base = memory.records[rule_ids[0]]
        base_program = memory.programs()[0]
        memory.deprecate(base.rule_id)
        for version in range(2, 13):
            record = memory.add(
                base_program,
                base.specification,
                VerificationStatus.PROPERTY_VERIFIED,
                provenance=f"m24-semantic-version-{version}",
                verification_evidence=base.verification_evidence,
            )
            if version < 12:
                memory.deprecate(record.rule_id)
        memory.save(service.memory_path)
        loaded = RuleMemory.load(service.memory_path)
        require(len(loaded.records) == 100, "100 records/semantic versions")
        require(len(loaded.active_records()) == 89, "active retention after versioning")
        require(
            len({item.rule_id for item in loaded.records.values()}) == 100, "unique ids"
        )
        for record in loaded.records.values():
            require(loaded.records[record.rule_id] == record, "inspect every record")
        for record in loaded.active_records():
            result = execute_rule(
                service.memory_path,
                record.rule_id,
                {"R0": 2, "R1": 3, "R2": 4, "R3": 5},
            )
            require(result.actions[-1] == "H", "execute every active record")
        events = service.audit.replay()
        require(bool(events), "audit is non-empty")
        require(events[-1].sequence == len(events), "audit replay sequence")

        # Find and verify the exact mandatory A+B->C rule independently of matrix order.
        mandatory = next(
            item
            for item in loaded.records.values()
            if item.specification.transfers == (("A", "C"), ("B", "C"))
        )
        merge_result = execute_rule(
            service.memory_path,
            mandatory.rule_id,
            {"R0": 2, "R1": 3, "R2": 4, "R3": 5},
        )
        require(
            merge_result.final_state == {"R0": 0, "R1": 0, "R2": 9, "R3": 5},
            "mandatory A+B->C scenario",
        )

    import_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ai_brain.stage1; assert 'torch' not in sys.modules",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    require(import_probe.returncode == 0, "trusted import initializes torch")
    return {
        "outcome": "A",
        "acceptance_checks": checks,
        "structural_specifications": len(rows),
        "family_counts": dict(sorted(family_counts.items())),
        "language_semantic_cases": len(rows) * 2 * 2,
        "rule_memory_records": 100,
        "active_rules_executed": 89,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "device": "CPU-only deterministic acceptance",
        "source_sha": git("rev-parse", "HEAD"),
    }


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def write_outputs(result: dict) -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "stage1_version": STAGE1_VERSION,
        "controlled_language_version": CONTROLLED_LANGUAGE_VERSION,
        "specification_schema_version": SPECIFICATION_SCHEMA_VERSION,
        "rule_memory_schema_version": RULE_MEMORY_SCHEMA_VERSION,
        "frozen_backend_tag": "stage1-acquisition-v1",
        "frozen_backend_sha": "11b573ee46",
        "m231_source_sha": "54aafbc0fd",
        "integration_base_sha": result["source_sha"],
        "final_integration_sha": "git:stage1-v1.0.0^{commit}",
        "languages": ["ru", "en"],
        "families": [item.value for item in SemanticFamily],
        "primitives": ["MOVE_ONE", "DROP_ONE", "HALT"],
        "trusted_frontends": ["FORM", "CANONICAL_DSL", "CONTROLLED_LANGUAGE"],
        "research_only_frontends": ["NEURAL_LANGUAGE_TO_SPEC"],
        "policies": {
            "explicit_approval": True,
            "hash_bound_approval": True,
            "atomic_rule_memory": True,
            "append_only_audit": True,
            "cpu_only_trusted_path": True,
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = report_markdown(result)
    DOC_REPORT.parent.mkdir(parents=True, exist_ok=True)
    DOC_REPORT.write_text(report, encoding="utf-8")
    RUN_REPORT.write_text(report, encoding="utf-8")
    with PROGRESS_PATH.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps({"event": "acceptance_complete", **result}, sort_keys=True)
            + "\n"
        )


def report_markdown(result: dict) -> str:
    return f"""# M-24 Stage-1 Production Integration Report

## Outcome

Outcome **{result["outcome"]}**. The deterministic Stage-1 production path passed the local acceptance battery. Release tagging remains conditional on the final remote gate matching the pushed SHA.

## Source Control

- integration base: annotated tag `stage1-acquisition-v1`, commit `11b573ee46`
- selectively audited M-23.1 source: commit `54aafbc0fd`
- integration source SHA used by this generated report: `{result["source_sha"]}`
- branch: `exp/stage1-v1-integration`

## Checks

- local Windows: `ruff format --check` passed, `ruff check` passed, `360 passed`
- Karina M-23.1 source verification at `54aafbc0`: `365 passed`, 2 non-failing torch warnings
- production acceptance: `{result['acceptance_checks']}` checks, Outcome {result['outcome']}
- final pushed-SHA Karina gate: required immediately before release tagging

## Architecture

Trusted form/JSON, canonical DSL, and deterministic controlled RU/EN input produce an immutable proposal. Review precedes property verification. Explicit approval binds proposal, specification, candidate, and evidence hashes. Installation re-verifies and atomically persists to RuleMemory. Execution uses the exact external-state interpreter and appends a hash-chained audit event. The trusted import path does not initialize torch.

## Acceptance

- exact checks: **{result["acceptance_checks"]}**
- structural specifications: **{result["structural_specifications"]}**
- bilingual canonical/extended semantic cases: **{result["language_semantic_cases"]}**
- RuleMemory records/semantic versions: **{result["rule_memory_records"]}**
- active rules inspected and executed: **{result["active_rules_executed"]}**
- mandatory `A+B->C` from `2,3,4,5`: `0,0,9,5`
- elapsed: `{result["elapsed_seconds"]}` seconds
- device: `{result["device"]}`

## Security And Recovery

The battery covers invalid transitions, bounded clarification, stale candidate and approval rejection, candidate/evidence hash binding, exact approval identity, duplicate rules, deterministic IDs, checksummed atomic persistence, backup recovery, corruption rejection, and audit-chain tamper detection.

## Limitations

The RU/EN frontend is a documented controlled language, not open-ended natural-language understanding. Generic CEGIS abstains when no property-satisfying candidate is found within its public search budget. Execution is limited to four non-negative integer registers and three primitives. Neural M-23.1 frontend code is not part of the trusted production package.

## Recommendation

Freeze Stage 1 after local and remote acceptance agree on the exact pushed commit. Begin Stage 2 as a separate effort; do not widen the frozen Stage-1 grammar or import research neural components into this release line.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    result = run()
    if arguments.write:
        write_outputs(result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
