"""Bind heterogeneous M-33.6k.2 evidence into public-safe readiness receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k2_readiness import (
    M336K2_REQUIRED_READINESS_EVIDENCE,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    if set(request) != {"output", "sources"}:
        raise M336K2ProtocolError("M336K2 evidence binding request fields changed")
    sources = request["sources"]
    if (
        not isinstance(sources, dict)
        or set(sources) != M336K2_REQUIRED_READINESS_EVIDENCE
    ):
        raise M336K2ProtocolError("M336K2 evidence binding set changed")
    output = Path(request["output"]).resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K2 evidence binding output must be fresh")
    output.mkdir(parents=True)
    receipts = []
    for name, spec in sorted(sources.items()):
        if not isinstance(spec, dict) or set(spec) != {
            "path",
            "hash_field",
            "expected_status",
        }:
            raise M336K2ProtocolError("M336K2 evidence binding source fields changed")
        source_path = Path(spec["path"]).resolve(strict=True)
        source = _object(source_path)
        body = dict(source)
        claimed = body.pop(spec["hash_field"], None)
        expected_status = spec["expected_status"]
        if (
            not isinstance(claimed, str)
            or len(claimed) != 64
            or content_hash(body) != claimed
            or (expected_status is not None and source.get("status") != expected_status)
        ):
            raise M336K2ProtocolError(f"M336K2 source evidence is invalid: {name}")
        receipt_body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K2_READINESS_EVIDENCE_BINDING",
            "evidence_name": name,
            "source_hash_field": spec["hash_field"],
            "source_claimed_hash": claimed,
            "source_bytes_hash": bytes_hash(source_path.read_bytes()),
            "source_status": expected_status,
            "status": "PASS",
        }
        receipt = {**receipt_body, "receipt_hash": content_hash(receipt_body)}
        target = output / f"{name}.json"
        target.write_text(
            canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
        )
        receipts.append((name, receipt["receipt_hash"]))
    manifest_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_READINESS_EVIDENCE_BINDING_MANIFEST",
        "evidence_count": len(receipts),
        "evidence_receipt_hashes": tuple(receipts),
        "status": "PASS",
    }
    manifest = {**manifest_body, "manifest_hash": content_hash(manifest_body)}
    (output / "binding_manifest.json").write_text(
        canonical_json(manifest) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(manifest))


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 evidence source is invalid JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 evidence source is not an object")
    return value


if __name__ == "__main__":
    main()
