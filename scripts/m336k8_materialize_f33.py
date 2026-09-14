"""Materialize or attest the phase-neutral M-33.6k.8 freeze."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K8FreezeManifest,
    attest_committed_m336k8_freeze,
    materialize_m336k8_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    args = parser.parse_args()
    value = _object(args.configuration.resolve(strict=True))
    if "attest" in value:
        if set(value) != {"attest", "repository", "git_executable", "output"}:
            raise M336K2ProtocolError("M336K8 attestation configuration changed")
        settings = value["attest"]
        if type(settings) is not dict or set(settings) != {
            "freeze_manifest",
            "exact_freeze_sha",
        }:
            raise M336K2ProtocolError("M336K8 attestation settings changed")
        manifest = M336K8FreezeManifest.from_dict(
            _object(Path(settings["freeze_manifest"]))
        )
        result = attest_committed_m336k8_freeze(
            Path(value["repository"]),
            Path(value["git_executable"]),
            freeze_manifest=manifest,
            exact_freeze_sha=settings["exact_freeze_sha"],
        )
        output = Path(value["output"]).resolve(strict=False)
        if output.exists():
            raise M336K2ProtocolError("M336K8 attestation output is stale")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            canonical_json(asdict(result)) + "\n", encoding="utf-8", newline="\n"
        )
        print(canonical_json(asdict(result)))
        return
    expected = {
        "repository",
        "git_executable",
        "exact_implementation_tip",
        "exact_qualification_sha",
        "readiness",
        "component_sources",
        "output",
        "expected_branch",
        "freeze_relative_root",
    }
    if set(value) != expected or type(value["component_sources"]) is not dict:
        raise M336K2ProtocolError("M336K8 freeze configuration changed")
    result = materialize_m336k8_freeze(
        repository=Path(value["repository"]),
        git_executable=Path(value["git_executable"]),
        exact_implementation_tip=value["exact_implementation_tip"],
        exact_qualification_sha=value["exact_qualification_sha"],
        readiness=Path(value["readiness"]),
        component_sources={
            name: Path(path) for name, path in value["component_sources"].items()
        },
        output=Path(value["output"]),
        expected_branch=value["expected_branch"],
        freeze_relative_root=value["freeze_relative_root"],
    )
    print(canonical_json(result))


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K8 JSON input is not an object")
    return value


if __name__ == "__main__":
    main()
