"""Strict public contracts and producer coverage for M-33.6f evaluation output."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition import m336d_contracts as _contract_core
from ai_brain.stage3.acquisition.m336d_contracts import (
    PublicArtifactRole,
    PublicArtifactTypeContract,
    PublicArtifactValidation,
    RecursiveFieldContract,
)
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
    M336E_PUBLIC_CONTRACTS,
    M336EPublicFinalArtifactContractRegistryV2,
    ProducerContractCompatibilityGate,
    PublicArtifactProducer,
    m336e_future_public_producers,
)
from ai_brain.stage3.acquisition.m336f_evaluation_artifacts import (
    M336F_SEMANTIC_EVALUATION_CONTRACT,
    M336F_TELEMETRY_CONTRACT,
    build_m336f_evaluation_telemetry_receipt,
    build_m336f_semantic_evaluation_artifact,
)


def _field(name: str, value_type: str, **kwargs) -> RecursiveFieldContract:
    return RecursiveFieldContract(name, value_type, **kwargs)


def _named_pair(name: str, value: RecursiveFieldContract) -> RecursiveFieldContract:
    return _field(
        name,
        "array",
        unique_items=True,
        sorted_items=True,
        item_contract=_field(
            "entry",
            "array",
            min_items=2,
            max_items=2,
            tuple_fields=(_field("name", "string"), value),
        ),
    )


def _contract(
    artifact_type: str,
    path_pattern: str,
    fields: tuple[RecursiveFieldContract, ...],
) -> PublicArtifactTypeContract:
    body = {
        "artifact_type": artifact_type,
        "path_pattern": path_pattern,
        "role": PublicArtifactRole.EVALUATION,
        "media_type": "application/json",
        "schema_version": M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
        "fields": fields,
        "expected_magic_hex": None,
        "minimum_bytes": None,
        "maximum_bytes": None,
    }
    return PublicArtifactTypeContract(**body, contract_hash=content_hash(body))


_HASH = _field("value", "string", pattern=r"[0-9a-f]{64}")
_STRING = _field("value", "string")
_INTEGER = _field("value", "integer", minimum=0)
_RATIO = _field("value", "string", pattern=r"(?:0\.[0-9]{6}|1\.000000|N/A)")

M336F_SEMANTIC_EVALUATION_ARTIFACT_CONTRACT = _contract(
    "m336f-semantic-evaluation",
    r"e21/semantic_evaluation\.json",
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _field(
            "contract_role",
            "string",
            enum_values=(M336F_SEMANTIC_EVALUATION_CONTRACT,),
        ),
        _named_pair("identities", _STRING),
        _named_pair("counts", _INTEGER),
        _named_pair("ratios", _RATIO),
        _named_pair("decisions", _STRING),
        _named_pair("hashes", _HASH),
        _named_pair("normalized_diagnostic_categories", _INTEGER),
        _named_pair("mismatch_manifest_hashes", _HASH),
        _field(
            "readiness_result",
            "string",
            enum_values=("PASS", "FAIL", "REVIEW_REQUIRED"),
        ),
        _field("artifact_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336F_EVALUATION_TELEMETRY_CONTRACT = _contract(
    "m336f-evaluation-telemetry",
    r"e21/evaluation_telemetry\.json",
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _field(
            "contract_role",
            "string",
            enum_values=(M336F_TELEMETRY_CONTRACT,),
        ),
        _field("platform", "string", enum_values=("windows", "karina")),
        _field("host_identity_hash", "string", pattern=r"[0-9a-f]{64}"),
        _named_pair(
            "operation_timings_seconds",
            _field("value", "string", pattern=r"[0-9]+(?:\.[0-9]+)?"),
        ),
        _field("peak_memory_bytes", "integer", minimum=0),
        _field("jdk_executable_hash", "string", pattern=r"[0-9a-f]{64}"),
        _named_pair("process_measurements", _INTEGER),
        _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336F_PUBLIC_CONTRACTS = (
    *M336E_PUBLIC_CONTRACTS,
    M336F_SEMANTIC_EVALUATION_ARTIFACT_CONTRACT,
    M336F_EVALUATION_TELEMETRY_CONTRACT,
)


class M336FPublicFinalArtifactContractRegistry(
    M336EPublicFinalArtifactContractRegistryV2
):
    """Extend v2 contracts without weakening the inherited strict validators."""

    def validate(
        self,
        relative_path: str,
        raw: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> PublicArtifactValidation:
        contract = self.match(relative_path)
        if contract.artifact_type not in {
            "m336f-semantic-evaluation",
            "m336f-evaluation-telemetry",
        }:
            return super().validate(relative_path, raw, expected_sha256=expected_sha256)
        del expected_sha256
        if any(marker in raw for marker in _contract_core._SOURCE_MARKERS):
            raise ValueError(
                "public artifact contains forbidden raw source/archive bytes"
            )
        text = raw.decode("utf-8", errors="strict")
        if (
            any(marker in text for marker in _contract_core._SECRET_MARKERS)
            or _contract_core._SECRET_VALUE.search(text)
            or _contract_core._JAVA_EXCERPT.search(text)
            or _contract_core._contains_absolute_path(text)
        ):
            raise ValueError("M-33.6f evaluation artifact contains forbidden content")
        value = _contract_core._strict_json(raw)
        _contract_core._reject_embedded_source_payload(value)
        _contract_core._validate_object(value, contract.fields, contract.artifact_type)
        hash_field = (
            "artifact_hash"
            if contract.artifact_type == "m336f-semantic-evaluation"
            else "receipt_hash"
        )
        body_value = dict(value)
        claimed = body_value.pop(hash_field)
        if content_hash(body_value) != claimed:
            raise ValueError("M-33.6f evaluation artifact content hash mismatch")
        body = {
            "relative_path": relative_path,
            "artifact_type": contract.artifact_type,
            "role": contract.role,
            "byte_size": len(raw),
            "sha256": bytes_hash(raw),
            "status": "PASS",
        }
        return PublicArtifactValidation(**body, validation_hash=content_hash(body))


M336F_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY = (
    M336FPublicFinalArtifactContractRegistry(M336F_PUBLIC_CONTRACTS)
)


def _semantic_fixture(variant: str) -> dict:
    readiness = {
        "SUCCESS": "PASS",
        "BLOCKED": "FAIL",
        "REVIEW_REQUIRED": "REVIEW_REQUIRED",
    }[variant]
    return asdict(
        build_m336f_semantic_evaluation_artifact(
            identities={"semantic_contract": M336F_SEMANTIC_EVALUATION_CONTRACT},
            counts={"wrong_trusted": 0},
            ratios={"safe_trust_coverage": "0.850000"},
            decisions={"evaluation": readiness},
            hashes={"threshold_manifest": "1" * 64},
            normalized_diagnostic_categories={},
            mismatch_manifest_hashes={"semantic": "2" * 64},
            readiness_result=readiness,
        )
    )


def _telemetry_fixture(platform: str) -> dict:
    return asdict(
        build_m336f_evaluation_telemetry_receipt(
            platform=platform.casefold(),
            host_identity_hash="3" * 64,
            operation_timings_seconds={"evaluation": "0.000000"},
            peak_memory_bytes=0,
            jdk_executable_hash="4" * 64,
            process_measurements={"compiler_invocations": 1},
        )
    )


def m336f_public_producers(legacy_acquisition_value: dict):
    """Return all inherited and M-33.6f public producers with every variant."""

    inherited = m336e_future_public_producers(legacy_acquisition_value)
    additions = (
        PublicArtifactProducer(
            producer_id="m336f.semantic-evaluation.v1",
            artifact_type="m336f-semantic-evaluation",
            relative_path="e21/semantic_evaluation.json",
            schema_version=M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
            success_variants=("SUCCESS",),
            blocked_variants=("BLOCKED",),
            review_required_variants=("REVIEW_REQUIRED",),
            produce=_semantic_fixture,
        ),
        PublicArtifactProducer(
            producer_id="m336f.evaluation-telemetry.v1",
            artifact_type="m336f-evaluation-telemetry",
            relative_path="e21/evaluation_telemetry.json",
            schema_version=M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
            success_variants=("WINDOWS", "KARINA"),
            blocked_variants=(),
            review_required_variants=(),
            produce=_telemetry_fixture,
        ),
    )
    return (*inherited, *additions)


def run_m336f_producer_contract_gate(legacy_acquisition_value: dict):
    return ProducerContractCompatibilityGate(
        M336F_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
        m336f_public_producers(legacy_acquisition_value),
    ).run()
