"""Build or verify the one canonical M-33.6k.13 freeze-readiness seal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileRegistry,
)
from ai_brain.stage3.acquisition.m336k13_plan import _fsync_parent
from ai_brain.stage3.acquisition.m336k13_readiness import (
    M336K13FreezeReadinessSeal,
    M336K13VerifiedReceipt,
    build_m336k13_freeze_readiness,
)


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K13 readiness input is invalid JSON") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K13 readiness input is not an object")
    return value


def _receipt(path: Path) -> M336K13VerifiedReceipt:
    return M336K13VerifiedReceipt.from_dict(_object(path))


def _build(args: argparse.Namespace) -> M336K13FreezeReadinessSeal:
    registry = M336KOfficialRouteProfileRegistry.from_dict(
        _object(args.profile_registry)
    )
    profile = M336KOfficialRouteProfile.from_dict(_object(args.active_profile))
    return build_m336k13_freeze_readiness(
        active_profile=profile,
        profile_registry=registry,
        official_acquisition_static_readiness=_receipt(
            args.official_acquisition_static_readiness
        ),
        official_unspent_state=_receipt(args.official_unspent_state),
        leak_report=_receipt(args.leak_report),
        current_storage_reservation=_receipt(args.storage_reservation),
        pre_resource_gate=_receipt(args.pre_resource_gate),
        post_resource_gate=_receipt(args.post_resource_gate),
        generation_supersession=_receipt(args.generation_supersession),
        evidence_binding_manifest=_receipt(args.evidence_binding_manifest),
        exact_implementation_tip=args.exact_implementation_tip,
        qualification_label=args.qualification_label,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-profile", type=Path, required=True)
    parser.add_argument("--profile-registry", type=Path, required=True)
    parser.add_argument(
        "--official-acquisition-static-readiness", type=Path, required=True
    )
    parser.add_argument("--official-unspent-state", type=Path, required=True)
    parser.add_argument("--leak-report", type=Path, required=True)
    parser.add_argument("--storage-reservation", type=Path, required=True)
    parser.add_argument("--pre-resource-gate", type=Path, required=True)
    parser.add_argument("--post-resource-gate", type=Path, required=True)
    parser.add_argument("--generation-supersession", type=Path, required=True)
    parser.add_argument("--evidence-binding-manifest", type=Path, required=True)
    parser.add_argument("--exact-implementation-tip", required=True)
    parser.add_argument("--qualification-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    readiness = _build(args)
    payload = (canonical_json(readiness.canonical_object()) + "\n").encode("utf-8")
    output = args.output.resolve(strict=False)
    if args.verify:
        if output.resolve(strict=True).read_bytes() != payload:
            raise M336K2ProtocolError("M336K13 readiness output differs")
        return
    if output.exists():
        raise FileExistsError("M336K13 readiness output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    _fsync_parent(output.parent)
    if output.read_bytes() != payload:
        raise M336K2ProtocolError("M336K13 readiness changed after creation")


if __name__ == "__main__":
    main()
