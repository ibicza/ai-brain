"""Materialize a non-authoritative V4 freeze for pre-Q36 launcher parity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K11_BRANCH,
    M336K11_READY_STATUS,
    M336K11_REQUIRED_FREEZE_COMPONENTS,
    M336K8FreezeManifest,
    materialize_m336k8_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(
        args.configuration.resolve(strict=True).read_text(encoding="utf-8")
    )
    expected = {
        "repository",
        "git_executable",
        "exact_implementation_tip",
        "readiness",
        "component_sources",
        "output",
        "freeze_relative_root",
    }
    if type(value) is not dict or set(value) != expected:
        raise M336K2ProtocolError("M336K11 prospective freeze configuration changed")
    if type(value["component_sources"]) is not dict:
        raise M336K2ProtocolError("M336K11 prospective component map changed")
    implementation = value["exact_implementation_tip"]
    result = materialize_m336k8_freeze(
        repository=Path(value["repository"]),
        git_executable=Path(value["git_executable"]),
        exact_implementation_tip=implementation,
        exact_qualification_sha=implementation,
        readiness=Path(value["readiness"]),
        component_sources={
            name: Path(path) for name, path in value["component_sources"].items()
        },
        output=Path(value["output"]),
        expected_branch=M336K11_BRANCH,
        freeze_relative_root=value["freeze_relative_root"],
        readiness_status=M336K11_READY_STATUS,
        freeze_role=M336K8FreezeManifest.ROLE_V4,
        required_components=M336K11_REQUIRED_FREEZE_COMPONENTS,
        build_receipt_name="prospective_freeze_build_receipt.json",
        allow_unpublished_qualification=True,
    )
    print(canonical_json(result))


if __name__ == "__main__":
    main()
