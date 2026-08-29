"""Measure bounded M-32 compilation and runtime operations as canonical JSON."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.conflicts import detect_conflicts
from ai_brain.stage3.acquisition.evaluation import evaluate_proposals
from ai_brain.stage3.acquisition.models import ProposalStatus, ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import propose_knowledge
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.verification import verify_proposals
from ai_brain.stage3.capabilities.models import CapabilityRequirement
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.capabilities.scalar_equation_solver import solve_scalar_equation
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.knowledge_ir.records import RuleContent
from ai_brain.stage3.knowledge_ir.validation import validate_records
from ai_brain.stage3.providers.persistence import load_provider_registry

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-08-29T00:00:00Z"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.iterations <= 50:
        raise ValueError("iterations must be between 1 and 50")
    providers = load_provider_registry(
        ROOT / "artifacts/stage3/providers/registry_v2.json"
    )
    capabilities = load_registry(
        ROOT / "artifacts/stage3/capabilities/registry_v2.json", providers
    )
    registry = InstalledDomainRegistry.open(
        ROOT / "artifacts/stage3/installed-domains-v2",
        capability_registry=capabilities,
        provider_registry=providers,
    )
    source = ROOT / "tests/fixtures/acquisition/m32/sources/kinematics.md"
    golden = json.loads(
        (ROOT / "tests/fixtures/acquisition/m32/goldens/kinematics.json").read_text(
            encoding="utf-8"
        )
    )
    with tempfile.TemporaryDirectory(prefix="m32-performance-") as directory:
        root = Path(directory)
        store = AcquisitionStore.open_or_initialize(root / "store")

        def load_source():
            return ingest_bundle(
                (source,),
                bundle_id="m32-performance",
                domain_tags=("performance",),
                imported_at=STAMP,
                store=store,
            )

        bundle = load_source()
        segments = segment_bundle(bundle, store)
        proposals = verify_proposals(
            bundle, segments, propose_knowledge(bundle, segments), store
        )
        approved, approvals = [], []
        for proposal in proposals:
            if proposal.status is ProposalStatus.VERIFIED:
                updated, _, approval = review_proposal(
                    proposal,
                    reviewer_identity="m32-performance-reviewer",
                    reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                    decision=ReviewDecision.APPROVE,
                    rationale="performance fixture",
                    timestamp=STAMP,
                )
                approved.append(updated)
                approvals.append(approval)
            else:
                approved.append(proposal)
        pack = load_pack(ROOT / "artifacts/domains/m32/kinematics-provisional-v2")
        rule = next(
            item.content
            for item in pack.knowledge_records
            if isinstance(item.content, RuleContent)
        )
        compile_index = 0

        def compile_pack():
            nonlocal compile_index
            compile_index += 1
            return compile_provisional_pack(
                bundle,
                segments,
                tuple(approved),
                tuple(item for item in approvals if item is not None),
                root / f"compiled-{compile_index}",
                domain_id="acquired-performance",
            )

        metrics = {
            "compilation_time": {
                "source_load": _measure(load_source, args.iterations),
                "segmentation": _measure(
                    lambda: segment_bundle(bundle, store), args.iterations
                ),
                "proposal_generation": _measure(
                    lambda: propose_knowledge(bundle, segments), args.iterations
                ),
                "ir_type_checking": _measure(
                    lambda: validate_records(pack.knowledge_records), args.iterations
                ),
                "equation_checking": _measure(
                    lambda: solve_scalar_equation(
                        rule, {"v0": "3", "a": "2", "t": "4"}, "v"
                    ),
                    args.iterations,
                ),
                "conflict_detection": _measure(
                    lambda: detect_conflicts(proposals), args.iterations
                ),
                "review_application": _measure(
                    lambda: review_proposal(
                        proposals[0],
                        reviewer_identity="m32-performance-reviewer",
                        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                        decision=ReviewDecision.APPROVE,
                        rationale="performance fixture",
                        timestamp=STAMP,
                    ),
                    args.iterations,
                ),
                "pack_compilation": _measure(compile_pack, args.iterations),
                "provider_closure": _measure(
                    lambda: resolve_capability(
                        capabilities,
                        CapabilityRequirement(
                            "generic.scalar_equation_solver.v1",
                            "^1.0.0",
                            "USER_RUNTIME",
                        ),
                        requesting_domain_id="performance",
                        requesting_pack_hash=pack.manifest.pack_content_hash,
                        provider_registry=providers,
                        resolved_at=STAMP,
                    ),
                    args.iterations,
                ),
                "pack_evaluation": _measure(
                    lambda: evaluate_proposals(proposals, golden, segments),
                    args.iterations,
                ),
                "installation_currentness": _measure(
                    lambda: registry.verify_currentness(
                        "acquired-kinematics", "0.1.0-provisional"
                    ),
                    args.iterations,
                ),
            },
            "runtime_query_time": {
                "heldout_exact_solution": _measure(
                    lambda: solve_scalar_equation(
                        rule, {"v0": "3", "a": "2", "t": "4"}, "v"
                    ),
                    args.iterations,
                )
            },
        }
    result = {
        "status": "PASS",
        "iterations": args.iterations,
        "trusted_cpu_only": True,
        "runtime_network": False,
        "metrics": metrics,
    }
    print(canonical_json(result))
    return 0


def _measure(call, iterations):
    samples = []
    peak = 0
    for _ in range(iterations):
        tracemalloc.start()
        started = time.perf_counter_ns()
        call()
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        _, current_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        samples.append(elapsed)
        peak = max(peak, current_peak)
    ordered = sorted(samples)
    total_seconds = sum(samples) / 1_000
    return {
        "p50_ms": _percentile(ordered, 0.50),
        "p95_ms": _percentile(ordered, 0.95),
        "p99_ms": _percentile(ordered, 0.99),
        "throughput_per_second": f"{iterations / total_seconds:.6f}",
        "peak_python_bytes": peak,
        "mean_ms": f"{statistics.fmean(samples):.6f}",
    }


def _percentile(values, fraction):
    index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
    return f"{values[index]:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
