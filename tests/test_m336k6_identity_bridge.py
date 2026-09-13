from pathlib import Path

import pytest

from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_freeze import (
    M336K5_REQUIRED_FREEZE_COMPONENTS,
    M336K6_LIFECYCLE_FREEZE_COMPONENTS,
    M336K6_REQUIRED_FREEZE_COMPONENTS,
)
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K6_ACQUISITION_RUN_ID,
    M336K6_EVALUATOR_RUN_ID,
    M336K6_PROTOCOL_RUN_ID,
    M336K6_ROUTE_VERSION,
    M336K6_SELECTOR_RUN_ID,
    M336K5ProtocolRunId,
    M336K5RouteVersion,
    build_m336k6_official_identity_bundle,
)
from ai_brain.stage3.acquisition.m336k5_registry import (
    M336K6_ROUTE_COMPONENTS,
    build_m336k5_route_manifest,
    build_m336k5_route_registry,
    build_m336k5_schema_registry,
)


def _hashes() -> dict[str, str]:
    return {
        "route_registry_hash": "1" * 64,
        "route_manifest_hash": "2" * 64,
        "acquisition_policy_hash": "3" * 64,
        "selector_policy_hash": "4" * 64,
        "evaluator_policy_hash": "5" * 64,
    }


def test_m336k6_official_identity_bundle_is_exact() -> None:
    bundle = build_m336k6_official_identity_bundle(**_hashes())

    assert bundle.route_version.value == M336K6_ROUTE_VERSION
    assert bundle.protocol_run_id.value == M336K6_PROTOCOL_RUN_ID
    assert bundle.acquisition_run_id.value == M336K6_ACQUISITION_RUN_ID
    assert bundle.selector_run_id.value == M336K6_SELECTOR_RUN_ID
    assert bundle.evaluator_run_id.value == M336K6_EVALUATOR_RUN_ID
    bundle.verify()


def test_m336k6_noncanonical_final_identity_is_rejected() -> None:
    with pytest.raises(M336K2ProtocolError, match="not canonical"):
        M336K5ProtocolRunId("m336k6.final-java.outcome-a.v2")

    with pytest.raises(M336K2ProtocolError, match="not canonical"):
        M336K5RouteVersion("m336k6.candidate-isolated-java-final-route.v2")


def test_m336k6_route_registry_binds_lifecycle_sources() -> None:
    repository = Path(__file__).resolve().parents[1]
    registry = build_m336k5_route_registry(repository, "m336k6")
    schemas = build_m336k5_schema_registry("m336k6")
    manifest = build_m336k5_route_manifest(registry, schemas)

    assert registry.route_version.value == M336K6_ROUTE_VERSION
    assert registry.missing_component_count == 0
    assert len(registry.components) == len(M336K6_ROUTE_COMPONENTS)
    assert {item.component_id.value for item in registry.components} >= {
        "m336k6.route-component.persistent-capsule.v1",
        "m336k6.route-component.preservation-cleanup.v1",
        "m336k6.route-component.extended-resource-monitor.v1",
    }
    assert manifest.route_version == registry.route_version


def test_m336k6_freeze_extension_preserves_all_f30_components() -> None:
    assert M336K5_REQUIRED_FREEZE_COMPONENTS < M336K6_REQUIRED_FREEZE_COMPONENTS
    assert (
        M336K6_REQUIRED_FREEZE_COMPONENTS - M336K5_REQUIRED_FREEZE_COMPONENTS
        == M336K6_LIFECYCLE_FREEZE_COMPONENTS
    )
