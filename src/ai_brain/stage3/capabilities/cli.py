from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.capabilities.models import CapabilityRequirement
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability

DEFAULT_REGISTRY = Path("artifacts/stage3/capabilities/registry_v1.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-brain-capabilities")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("capability_id")
    commands.add_parser("verify")
    resolve = commands.add_parser("resolve")
    resolve.add_argument("capability_id")
    resolve.add_argument("--version-range", default="*")
    resolve.add_argument("--context", default="USER_RUNTIME")
    resolve.add_argument("--domain", default="cli.request")
    resolve.add_argument("--pack-hash", default="0" * 64)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_registry(args.registry)
    if args.command == "list":
        result = {
            "status": "OK",
            "capabilities": [
                {
                    "capability_id": x.capability_id,
                    "version": x.version,
                    "status": x.status.value,
                }
                for x in registry.descriptors
            ],
        }
    elif args.command == "show":
        result = asdict(registry.descriptor(args.capability_id))
    elif args.command == "verify":
        registry.verify()
        result = {
            "status": "VERIFIED",
            "descriptor_count": len(registry.descriptors),
            "registry_hash": registry.registry_hash,
            "runtime_network": False,
            "imports_torch": False,
        }
    else:
        hashes = {
            x.provider_id: x.provider_implementation_hash for x in registry.descriptors
        }
        resolution = resolve_capability(
            registry,
            CapabilityRequirement(args.capability_id, args.version_range, args.context),
            requesting_domain_id=args.domain,
            requesting_pack_hash=args.pack_hash,
            provider_hashes=hashes,
        )
        result = asdict(resolution)
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
