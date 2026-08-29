"""Execute sealed held-out tasks through installed persistent tutor/public DTO flow."""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from pathlib import Path

from ai_brain.stage2.conversation.generic_service import (
    GenericConversationalTutorService,
)
from ai_brain.stage2.education.generic_service import GenericEducationalService
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.domains.education import GenericEducationalDomainProvider
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.providers.persistence import load_provider_registry

ROOT = Path(__file__).resolve().parents[1]
TRUSTED_STATUSES = {"ANSWERED", "SOLVED_EXACT"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--providers",
        type=Path,
        default=ROOT / "artifacts/stage3/m33/provider_registry.json",
    )
    parser.add_argument(
        "--capabilities",
        type=Path,
        default=ROOT / "artifacts/stage3/m33/capability_registry.json",
    )
    args = parser.parse_args(argv)
    if args.state.exists() or args.output.exists():
        raise FileExistsError("held-out runtime state and report must be absent")
    providers = load_provider_registry(args.providers)
    capabilities = load_registry(args.capabilities, providers)
    registry = InstalledDomainRegistry.open(
        args.registry,
        capability_registry=capabilities,
        provider_registry=providers,
    )
    tasks = _read_jsonl(args.heldout)
    services = {}
    results = []
    tracemalloc.start()
    started = time.perf_counter_ns()
    for index, task in enumerate(tasks):
        bundle_id = task["bundle_id"]
        if bundle_id not in services:
            provider = GenericEducationalDomainProvider.from_installed(
                registry,
                bundle_id,
                "1.0.0-m33",
                state_root=args.state / bundle_id / "education",
            )
            tutor = GenericConversationalTutorService(
                GenericEducationalService(provider),
                state_root=args.state / bundle_id,
            )
            conversation = tutor.start(f"m33-heldout-{bundle_id}")
            services[bundle_id] = (tutor, conversation.conversation_id)
        tutor, conversation_id = services[bundle_id]
        task_started = time.perf_counter_ns()
        response = tutor.query(conversation_id, task["request"])
        latency = time.perf_counter_ns() - task_started
        observed_status = response.get("status")
        expected = task.get("expected", {})
        correct = observed_status == task["expected_status"] and all(
            response.get(key) == value for key, value in expected.items()
        )
        trusted = observed_status in TRUSTED_STATUSES
        provenance = bool(response.get("pack_hash")) and bool(
            response.get("capability_receipt_hashes")
        )
        results.append(
            {
                "task_hash": task["semantic_hash"],
                "bundle_id": bundle_id,
                "observed_status": observed_status,
                "correct": correct,
                "trusted": trusted,
                "public_provenance": provenance,
                "response_hash": content_hash(response),
                "latency_ns": latency,
                "ordinal": index,
            }
        )
    elapsed = time.perf_counter_ns() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    latencies = sorted(item["latency_ns"] for item in results)
    persistence = {
        bundle_id: tutor.verify_persistence()
        for bundle_id, (tutor, _) in services.items()
    }
    supported = tuple(item for item in results if item["trusted"])
    report = {
        "status": (
            "PASS"
            if all(item["correct"] for item in results)
            and all(
                not item["trusted"] or item["public_provenance"] for item in results
            )
            else "FAIL"
        ),
        "task_count": len(results),
        "correct_count": sum(item["correct"] for item in results),
        "trusted_count": len(supported),
        "wrong_trusted": sum(not item["correct"] for item in supported),
        "coverage": _rate(len(supported), len(results)),
        "abstention": _rate(len(results) - len(supported), len(results)),
        "latency_ns": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        },
        "throughput_per_second": (
            "N/A" if not elapsed else f"{len(results) / (elapsed / 1_000_000_000):.6f}"
        ),
        "peak_python_bytes": peak,
        "persistence": persistence,
        "results": results,
    }
    report = {**report, "report_hash": content_hash(report)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        canonical_json(
            {key: value for key, value in report.items() if key != "results"}
        )
    )
    return 0 if report["status"] == "PASS" else 1


def _rate(numerator: int, denominator: int) -> str:
    return "N/A" if denominator == 0 else f"{numerator / denominator:.6f}"


def _percentile(values: list[int], percentile: int):
    if not values:
        return "N/A"
    return values[min(len(values) - 1, (len(values) * percentile + 99) // 100 - 1)]


def _read_jsonl(path: Path):
    return tuple(
        json.loads(line, object_pairs_hook=_strict_object)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate held-out JSON field")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
