"""External pre-proposal golden seal and immutable evaluation configuration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_goldens import JavaGoldenManifest

_CONFIG = Path(__file__).with_name("data") / "m342_java_trust_config.json"
_CONFIG_ARTIFACT_HASH = (
    "eadb6057eefd341c92b50a73bad4cc845f87d2429ae444cad1d602f0b88c5683"
)


@dataclass(frozen=True)
class GoldenSealReceipt:
    schema_version: int
    source_manifest_hash: str
    target_census_hash: str
    golden_manifest_hash: str
    oracle_implementation_hash: str
    seal_authority_identity: str
    seal_authority_type: str
    sealing_phase: str
    sealing_ref: str
    seal_receipt_hash: str


@dataclass(frozen=True)
class JavaTrustEvaluationConfig:
    schema_version: int
    config_id: str
    expected_golden_seal_hash: str
    expected_parser_common_artifact_hash: str
    expected_evidence_policy_hash: str
    expected_source_manifest_hash: str
    expected_target_census_hash: str
    expected_oracle_implementation_hash: str
    expected_sealing_phase: str
    expected_sealing_ref: str
    expected_authority_identity: str
    expected_authority_type: str
    config_hash: str


def load_java_trust_evaluation_config() -> JavaTrustEvaluationConfig:
    raw = _CONFIG.read_bytes()
    if bytes_hash(raw) != _CONFIG_ARTIFACT_HASH:
        raise ValueError("immutable Java evaluation configuration bytes changed")
    row = json.loads(raw.decode("utf-8"))
    claimed = row.pop("config_hash")
    if content_hash(row) != claimed:
        raise ValueError("Java evaluation configuration hash mismatch")
    return JavaTrustEvaluationConfig(**row, config_hash=claimed)


def load_golden_seal_receipt(path: Path) -> GoldenSealReceipt:
    row = json.loads(path.read_text(encoding="utf-8"))
    if set(row) != set(GoldenSealReceipt.__dataclass_fields__):
        raise ValueError("golden seal receipt schema mismatch")
    receipt = GoldenSealReceipt(**row)
    verify_golden_seal_receipt(receipt)
    return receipt


def verify_golden_seal_receipt(
    receipt: GoldenSealReceipt,
    golden_manifest: JavaGoldenManifest | None = None,
    config: JavaTrustEvaluationConfig | None = None,
) -> None:
    body = asdict(receipt)
    claimed = body.pop("seal_receipt_hash")
    if content_hash(body) != claimed or receipt.schema_version != 1:
        raise ValueError("golden seal receipt hash mismatch")
    if golden_manifest is not None and (
        receipt.golden_manifest_hash != golden_manifest.manifest_hash
        or receipt.source_manifest_hash != golden_manifest.source_manifest_hash
        or receipt.target_census_hash != golden_manifest.target_census_hash
        or receipt.oracle_implementation_hash
        != golden_manifest.oracle_implementation_hash
    ):
        raise ValueError("golden seal does not bind the supplied semantic manifest")
    if config is not None:
        if config != load_java_trust_evaluation_config():
            raise ValueError("Java evaluation configuration is not immutable")
        expected = (
            config.expected_golden_seal_hash,
            config.expected_source_manifest_hash,
            config.expected_target_census_hash,
            config.expected_oracle_implementation_hash,
            config.expected_sealing_phase,
            config.expected_sealing_ref,
            config.expected_authority_identity,
            config.expected_authority_type,
        )
        actual = (
            receipt.seal_receipt_hash,
            receipt.source_manifest_hash,
            receipt.target_census_hash,
            receipt.oracle_implementation_hash,
            receipt.sealing_phase,
            receipt.sealing_ref,
            receipt.seal_authority_identity,
            receipt.seal_authority_type,
        )
        if actual != expected:
            raise ValueError("golden seal is outside immutable evaluation authority")
