"""Materialize the canonical M-33.6k.9 profile/admission component set."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k9_admission import (
    M336K9_CONTROLLER_ADMISSION_CONTRACT,
    M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH,
    run_m336k_official_profile_coverage_gate,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    m336k_official_profile_registry,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-id", default="m336k8-final-v2")
    args = parser.parse_args()
    output = args.output.resolve(strict=False)
    if output.exists():
        raise M336K2ProtocolError("M336K9 profile component output is stale")
    registry = m336k_official_profile_registry()
    profile = registry.profile(args.profile_id)
    coverage = run_m336k_official_profile_coverage_gate()
    output.mkdir(parents=True)
    values = {
        "official_profile_registry": registry.canonical_object(),
        "active_official_profile": profile.canonical_object(),
        "profile_coverage_gate": coverage.canonical_object(),
        "controller_admission_contract": {
            **M336K9_CONTROLLER_ADMISSION_CONTRACT,
            "contract_hash": M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH,
        },
    }
    for name, value in values.items():
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    print(canonical_json({name: value for name, value in values.items()}))


if __name__ == "__main__":
    main()
