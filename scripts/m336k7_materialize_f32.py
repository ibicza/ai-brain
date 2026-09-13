"""Materialize or attest the exact M-33.6k.7 F32 freeze."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k7_freeze import (
    M336K7FreezeManifest,
    attest_committed_m336k7_f32,
    materialize_m336k7_f32,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--attest", action="store_true")
    args = parser.parse_args()
    value = _object(args.configuration.resolve(strict=True))
    if args.attest:
        expected = {
            "repository",
            "git_executable",
            "freeze_manifest",
            "exact_f32_sha",
            "output",
        }
        if set(value) != expected:
            raise M336K2ProtocolError("M336K7 attestation configuration changed")
        manifest = M336K7FreezeManifest.from_dict(
            _object(Path(value["freeze_manifest"]).resolve(strict=True))
        )
        result = attest_committed_m336k7_f32(
            Path(value["repository"]),
            Path(value["git_executable"]),
            freeze_manifest=manifest,
            exact_f32_sha=value["exact_f32_sha"],
        )
        output = Path(value["output"]).resolve(strict=False)
        if output.exists():
            raise M336K2ProtocolError("M336K7 attestation output is stale")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            canonical_json(result.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(canonical_json(asdict(result)))
        return
    expected = {
        "repository",
        "git_executable",
        "exact_implementation_tip",
        "exact_q32_sha",
        "readiness",
        "component_sources",
        "output",
        "expected_branch",
        "freeze_relative_root",
    }
    if set(value) != expected or type(value["component_sources"]) is not dict:
        raise M336K2ProtocolError("M336K7 freeze configuration changed")
    result = materialize_m336k7_f32(
        repository=Path(value["repository"]),
        git_executable=Path(value["git_executable"]),
        exact_implementation_tip=value["exact_implementation_tip"],
        exact_q32_sha=value["exact_q32_sha"],
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
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K7 configuration JSON is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K7 configuration JSON is not an object")
    return value


if __name__ == "__main__":
    main()
