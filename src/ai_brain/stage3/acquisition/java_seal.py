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
    semantic_manifest_hash: str | None = None
    diagnostic_manifest_hash: str | None = None


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
    expected_semantic_manifest_hash: str | None = None
    expected_diagnostic_manifest_hash: str | None = None
    authority_root_hash: str | None = None


def load_java_trust_evaluation_config() -> JavaTrustEvaluationConfig:
    raw = _CONFIG.read_bytes()
    if bytes_hash(raw) != _CONFIG_ARTIFACT_HASH:
        raise ValueError("immutable Java evaluation configuration bytes changed")
    row = json.loads(raw.decode("utf-8"))
    claimed = row.pop("config_hash")
    if content_hash(row) != claimed:
        raise ValueError("Java evaluation configuration hash mismatch")
    return JavaTrustEvaluationConfig(**row, config_hash=claimed)


def load_external_java_trust_evaluation_config(
    path: Path,
    *,
    expected_config_sha256: str,
    authority_root_hash: str,
) -> JavaTrustEvaluationConfig:
    """Load config only when two independently supplied authority values agree."""

    raw = path.read_bytes()
    if bytes_hash(raw) != expected_config_sha256:
        raise ValueError("external Java evaluation config bytes are unauthorized")
    row = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    if set(row) != set(JavaTrustEvaluationConfig.__dataclass_fields__):
        raise ValueError("external Java evaluation config schema mismatch")
    claimed = row.pop("config_hash")
    if content_hash(row) != claimed:
        raise ValueError("external Java evaluation config hash mismatch")
    config = JavaTrustEvaluationConfig(**row, config_hash=claimed)
    if config.schema_version != 2 or config.authority_root_hash != authority_root_hash:
        raise ValueError("external Java evaluation authority root mismatch")
    return config


def load_golden_seal_receipt(path: Path) -> GoldenSealReceipt:
    row = json.loads(path.read_text(encoding="utf-8"))
    legacy = set(GoldenSealReceipt.__dataclass_fields__) - {
        "semantic_manifest_hash",
        "diagnostic_manifest_hash",
    }
    if set(row) not in (
        legacy,
        set(GoldenSealReceipt.__dataclass_fields__),
    ):
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
    if receipt.schema_version == 1:
        body.pop("semantic_manifest_hash")
        body.pop("diagnostic_manifest_hash")
    if content_hash(body) != claimed or receipt.schema_version not in {1, 2}:
        raise ValueError("golden seal receipt hash mismatch")
    if golden_manifest is not None and (
        receipt.golden_manifest_hash != golden_manifest.manifest_hash
        or receipt.source_manifest_hash != golden_manifest.source_manifest_hash
        or receipt.target_census_hash != golden_manifest.target_census_hash
        or receipt.oracle_implementation_hash
        != golden_manifest.oracle_implementation_hash
        or (
            receipt.schema_version == 2
            and (
                receipt.semantic_manifest_hash != golden_manifest.semantic_manifest_hash
                or receipt.diagnostic_manifest_hash
                != golden_manifest.diagnostic_manifest_hash
            )
        )
    ):
        raise ValueError("golden seal does not bind the supplied semantic manifest")
    if config is not None:
        if config.schema_version == 1 and config != load_java_trust_evaluation_config():
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
            config.expected_semantic_manifest_hash,
            config.expected_diagnostic_manifest_hash,
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
            receipt.semantic_manifest_hash,
            receipt.diagnostic_manifest_hash,
        )
        if actual != expected:
            raise ValueError("golden seal is outside immutable evaluation authority")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Java evaluation config JSON key")
        result[key] = value
    return result
