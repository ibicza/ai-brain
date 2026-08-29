from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash, utc_now
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityResolutionReceipt,
)
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.domains.approval import (
    DomainPackApprovalEnvelope,
    PackApprovalDecision,
    approve_pack,
)
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import validate_pack

DEFAULT_CAPABILITIES = Path("artifacts/stage3/capabilities/registry_v1.json")
DEFAULT_INSTALLED = Path(".ai-brain/installed-domains")


def build_parser():
    p = argparse.ArgumentParser(prog="ai-brain-domains")
    p.add_argument("--registry-root", type=Path, default=DEFAULT_INSTALLED)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("verify-pack", "approve-pack"):
        q = sub.add_parser(name)
        q.add_argument("pack", type=Path)
        q.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    sub.choices["approve-pack"].add_argument("--reviewer", required=True)
    sub.choices["approve-pack"].add_argument("--output", type=Path, required=True)
    q = sub.add_parser("install")
    q.add_argument("pack", type=Path)
    q.add_argument("approval", type=Path)
    sub.add_parser("list")
    q = sub.add_parser("show")
    q.add_argument("domain_id")
    q.add_argument("--version")
    for name in ("deprecate", "uninstall"):
        q = sub.add_parser(name)
        q.add_argument("domain_id")
        q.add_argument("version")
    sub.add_parser("verify-registry")
    q = sub.add_parser("export")
    q.add_argument("output", type=Path)
    q = sub.add_parser("backup")
    q.add_argument("output", type=Path)
    q = sub.add_parser("restore")
    q.add_argument("backup", type=Path)
    q.add_argument("target", type=Path)
    return p


def _resolve(pack, path):
    registry = load_registry(path)
    provider_hashes = {
        x.provider_id: x.provider_implementation_hash for x in registry.descriptors
    }
    receipts = []
    for requirement in pack.manifest.required_capabilities:
        value = resolve_capability(
            registry,
            requirement,
            requesting_domain_id=pack.manifest.domain_id,
            requesting_pack_hash=pack.manifest.pack_content_hash,
            provider_hashes=provider_hashes,
        )
        if value.receipt is None:
            raise ValueError(f"NEEDS_NEW_CAPABILITY: {requirement.capability_id}")
        receipts.append(value.receipt)
    return tuple(receipts)


def _approval_bundle(path):
    row = json.loads(path.read_text(encoding="utf-8"))
    a = row["approval"]
    a["reviewer_type"] = ActorIdentityType(a["reviewer_type"])
    a["decision"] = PackApprovalDecision(a["decision"])
    a["source_binding_hashes"] = tuple(a["source_binding_hashes"])
    a["capability_resolution_receipt_hashes"] = tuple(
        a["capability_resolution_receipt_hashes"]
    )
    approval = DomainPackApprovalEnvelope(**a)
    receipts = []
    for x in row["resolutions"]:
        x["dependency_capabilities"] = tuple(x["dependency_capabilities"])
        x["authority_class"] = AuthorityClass(x["authority_class"])
        receipts.append(CapabilityResolutionReceipt(**x))
    return approval, tuple(receipts)


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.command in {"verify-pack", "approve-pack"}:
        pack = load_pack(a.pack)
        report = validate_pack(pack)
        receipts = _resolve(pack, a.capabilities)
        if a.command == "verify-pack":
            result = {**report, "capability_resolutions": len(receipts)}
        else:
            approval = approve_pack(
                pack_hash=pack.manifest.pack_content_hash,
                knowledge_ir_schema=1,
                concept_graph_hash=pack.manifest.concept_graph_hash,
                source_binding_hashes=pack.manifest.source_binding_hashes,
                capability_resolution_receipt_hashes=tuple(
                    x.receipt_hash for x in receipts
                ),
                validation_report_hash=content_hash(report),
                evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
                reviewer_identity=a.reviewer,
                reviewer_type=ActorIdentityType.USER,
                decision=PackApprovalDecision.APPROVE,
                policy_version="m31.1",
                timestamp=utc_now(),
            )
            bundle = {
                "approval": asdict(approval),
                "resolutions": [asdict(x) for x in receipts],
            }
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(
                canonical_json(bundle) + "\n", encoding="utf-8", newline="\n"
            )
            result = {
                "status": "APPROVED",
                "approval_hash": approval.approval_hash,
                "output": str(a.output),
            }
    elif a.command == "restore":
        registry = InstalledDomainRegistry.restore(a.backup, a.target)
        result = registry.verify()
    else:
        registry = InstalledDomainRegistry.open_or_initialize(a.registry_root)
        if a.command == "install":
            approval, receipts = _approval_bundle(a.approval)
            result = asdict(registry.install(load_pack(a.pack), approval, receipts))
        elif a.command == "list":
            result = {"status": "OK", "domains": [asdict(x) for x in registry.list()]}
        elif a.command == "show":
            result = asdict(registry.show(a.domain_id, a.version))
        elif a.command == "deprecate":
            result = asdict(registry.deprecate(a.domain_id, a.version))
        elif a.command == "uninstall":
            result = registry.uninstall(a.domain_id, a.version)
        elif a.command == "verify-registry":
            result = registry.verify()
        elif a.command == "export":
            result = registry.export(a.output)
        elif a.command == "backup":
            result = registry.backup(a.output)
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
