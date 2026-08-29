"""Resolve, exactly approve, and install frozen M-33 packs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.capabilities.models import ResolutionStatus
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.persistence import load_provider_registry

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--timestamp", required=True)
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
    providers = load_provider_registry(args.providers)
    capabilities = load_registry(args.capabilities, providers)
    registry = InstalledDomainRegistry.open_or_initialize(
        args.registry,
        capability_registry=capabilities,
        provider_registry=providers,
    )
    installed = []
    for pack_root in sorted((args.artifacts / "packs").iterdir()):
        pack = load_pack(pack_root)
        receipts = {}
        for requirement in pack.manifest.required_capabilities:
            descriptor = capabilities.descriptor(requirement.capability_id)
            resolution = resolve_capability(
                capabilities,
                requirement,
                requesting_domain_id=pack.manifest.domain_id,
                requesting_pack_hash=pack.manifest.pack_content_hash,
                provider_registry=providers,
                required_input_schema_hash=descriptor.input_schema_hash,
                required_output_schema_hash=descriptor.output_schema_hash,
                resolved_at=args.timestamp,
            )
            if resolution.status is not ResolutionStatus.RESOLVED:
                raise ValueError("M-33 pack capability closure is unresolved")
            for receipt in resolution.closure_receipts:
                receipts.setdefault(receipt.receipt_hash, receipt)
        closure = tuple(receipts.values())
        validation = validate_pack(pack)
        approval = approve_pack(
            pack_hash=pack.manifest.pack_content_hash,
            knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
            concept_graph_hash=pack.manifest.concept_graph_hash,
            source_binding_hashes=pack.manifest.source_binding_hashes,
            capability_resolution_receipt_hashes=tuple(
                item.receipt_hash for item in closure
            ),
            validation_report_hash=content_hash(validation),
            evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
            reviewer_identity="m33.executable-pack-evaluator.v1",
            reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
            decision=PackApprovalDecision.APPROVE,
            policy_version="m33.exact-pack-installation.v1",
            timestamp=args.timestamp,
        )
        (pack_root / "approval.json").write_text(
            canonical_json(
                {
                    "approval": asdict(approval),
                    "resolutions": [asdict(item) for item in closure],
                }
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        result = registry.install(
            load_pack(pack_root),
            approval,
            closure,
            installed_at=args.timestamp,
        )
        installed.append(asdict(result))
    report = {
        "status": "INSTALLED",
        "domains": installed,
        "registry_verification": registry.verify(),
    }
    report = {**report, "report_hash": content_hash(report)}
    output = args.artifacts / "installation_report.json"
    output.write_text(canonical_json(report) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
