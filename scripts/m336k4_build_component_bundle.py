"""Overlay typed M-33.6k.4 identities onto a freshly built native bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k4_authorization import (
    build_m336k4_final_authorization,
)
from ai_brain.stage3.acquisition.m336k4_identity import (
    M336K4AcquisitionRunId,
    M336K4EvaluatorRunId,
    M336K4ExecutionMode,
    M336K4ProtocolRunId,
    M336K4RouteIdentityBundle,
    M336K4SelectorRunId,
    build_m336k4_official_identity_bundle,
)
from ai_brain.stage3.acquisition.m336k4_registry import (
    build_m336k4_route_manifest,
    build_m336k4_route_registry,
    build_m336k4_schema_registry,
)
from ai_brain.stage3.acquisition.m336k4_request import (
    M336K4_FINAL_REQUEST_BUILDER_HASH,
    M336K4_FINAL_REQUEST_CONTRACT,
)

_LABEL = re.compile(r"[a-z0-9][a-z0-9-]{3,63}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    expected = {
        "repository",
        "legacy_bundle",
        "exact_implementation_tip",
        "exact_q29_sha",
        "branch_ref",
        "readiness_hash",
        "q_readiness",
        "q_evidence_manifest",
        "identity_mode",
        "disposable_label",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K4 component bundle request fields changed")
    repository = Path(request["repository"]).resolve(strict=True)
    legacy = Path(request["legacy_bundle"]).resolve(strict=True)
    output = Path(request["output"]).resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K4 component bundle output is stale or public")
    output.mkdir(parents=True)
    sources = {
        path.stem: path
        for path in legacy.glob("*.json")
        if path.name != "bundle_receipt.json"
    }
    if "candidate_pool" not in sources or "final_authorization" not in sources:
        raise M336K2ProtocolError("M336K4 legacy component closure is incomplete")
    for name, source in sources.items():
        shutil.copyfile(source, output / f"{name}.json")
    replacements = {
        "@IMPLEMENTATION_TIP@": request["exact_implementation_tip"],
        "@Q_SHA@": request["exact_q29_sha"],
        "@BRANCH_REF@": request["branch_ref"],
        "@READINESS_HASH@": request["readiness_hash"],
    }
    for path in output.glob("*.json"):
        value = _rehash_top_level(_replace(_object(path), replacements))
        path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    for name, source in (
        ("q28_readiness", request["q_readiness"]),
        ("q28_evidence_manifest", request["q_evidence_manifest"]),
    ):
        value = _rehash_top_level(_object(Path(source)))
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    registry = build_m336k4_route_registry(repository)
    schemas = build_m336k4_schema_registry()
    route = build_m336k4_route_manifest(registry, schemas)
    acquisition = _object(output / "acquisition_policy.json")
    acquisition.pop("acquisition_policy_hash", None)
    selector = _object(output / "selector_policy.json")
    selector.pop("policy_hash", None)
    threshold = _object(output / "threshold_manifest.json")
    mode = request["identity_mode"]
    label = request["disposable_label"]
    if mode == "OFFICIAL":
        acquisition_id = "m336k4.final-java.global-acquisition.v1"
        selector_id = "m336k4.final-java.selector.v1"
        evaluator_id = "m336k4.final-java.evaluator.v1"
    elif mode == "DISPOSABLE" and isinstance(label, str) and _LABEL.fullmatch(label):
        acquisition_id = f"m336k4.disposable.{label}.acquisition.v1"
        selector_id = f"m336k4.disposable.{label}.selector.v1"
        evaluator_id = f"m336k4.disposable.{label}.evaluator.v1"
    else:
        raise M336K2ProtocolError("M336K4 component identity mode is invalid")
    acquisition.update(
        {
            "contract_role": "M336K4_CANDIDATE_ISOLATED_ACQUISITION_POLICY",
            "policy_version": "m336k4.candidate-isolated-final.v1",
            "acquisition_run_id": acquisition_id,
        }
    )
    acquisition = {
        **acquisition,
        "acquisition_policy_hash": content_hash(acquisition),
    }
    selector.update(
        {
            "contract_role": "M336K4_COUNT_NEUTRAL_SELECTOR_POLICY",
            "selector_run_id": selector_id,
        }
    )
    selector = {**selector, "policy_hash": content_hash(selector)}
    evaluator_body = {
        "schema_version": 1,
        "contract_role": "M336K4_INDEPENDENT_EVALUATOR_POLICY",
        "evaluator_run_id": evaluator_id,
        "threshold_manifest_hash": threshold["threshold_manifest_hash"],
        "reservation_limit": 1,
        "retry_limit": 0,
        "goldens_after_reservation": True,
        "production_evaluator_reads": 0,
    }
    evaluator = {**evaluator_body, "policy_hash": content_hash(evaluator_body)}
    if mode == "OFFICIAL":
        bundle = build_m336k4_official_identity_bundle(
            route_registry_hash=registry.registry_hash,
            route_manifest_hash=route.manifest_hash,
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            selector_policy_hash=selector["policy_hash"],
            evaluator_policy_hash=evaluator["policy_hash"],
        )
    else:
        bundle = M336K4RouteIdentityBundle.build(
            route_version=registry.route_version,
            protocol_run_id=M336K4ProtocolRunId(f"m336k4.disposable.{label}.v1"),
            acquisition_run_id=M336K4AcquisitionRunId(acquisition_id),
            selector_run_id=M336K4SelectorRunId(selector_id),
            evaluator_run_id=M336K4EvaluatorRunId(evaluator_id),
            execution_mode=M336K4ExecutionMode("FINAL"),
            route_registry_hash=registry.registry_hash,
            route_manifest_hash=route.manifest_hash,
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            selector_policy_hash=selector["policy_hash"],
            evaluator_policy_hash=evaluator["policy_hash"],
        )
    legacy_authorization = _object(output / "final_authorization.json")
    authorization = build_m336k4_final_authorization(
        bundle=bundle,
        exact_implementation_tip=request["exact_implementation_tip"],
        exact_q29_sha=request["exact_q29_sha"],
        branch_ref=request["branch_ref"],
        candidate_pool_hash=legacy_authorization["candidate_pool_hash"],
        acquisition_policy_hash=acquisition["acquisition_policy_hash"],
        archive_policy_hash=legacy_authorization["archive_policy_hash"],
        candidate_terminal_policy_hash=legacy_authorization[
            "candidate_terminal_policy_hash"
        ],
        global_continuation_policy_hash=legacy_authorization[
            "global_continuation_policy_hash"
        ],
        route_manifest_hash=route.manifest_hash,
        route_registry_hash=registry.registry_hash,
        schema_registry_hash=schemas.registry_hash,
        readiness_hash=request["readiness_hash"],
        executable_dependency_manifest_hash=legacy_authorization[
            "executable_dependency_manifest_hash"
        ],
        python_environment_manifest_hash=legacy_authorization[
            "python_environment_manifest_hash"
        ],
        authority_statement_hash=legacy_authorization["authority_statement_hash"],
        disclosure_registry_manifest_hash=legacy_authorization[
            "disclosure_registry_manifest_hash"
        ],
        selector_policy_hash=selector["policy_hash"],
        evaluator_policy_hash=evaluator["policy_hash"],
        allowed_network_hosts=tuple(legacy_authorization["allowed_network_hosts"]),
        minimum_candidate_families=legacy_authorization["minimum_candidate_families"],
        minimum_organizations=legacy_authorization["minimum_organizations"],
        maximum_candidates_per_organization=legacy_authorization[
            "maximum_candidates_per_organization"
        ],
        acquisition_reservation_limit=1,
        selector_reservation_limit=1,
        evaluator_reservation_limit=1,
        candidate_retry_limit=0,
        candidate_replacement_limit=0,
        pre_freeze_source_body_bytes=0,
    )
    builder = {
        **M336K4_FINAL_REQUEST_CONTRACT,
        "builder_hash": M336K4_FINAL_REQUEST_BUILDER_HASH,
    }
    values = {
        "acquisition_policy": acquisition,
        "selector_policy": selector,
        "evaluator_policy": evaluator,
        "typed_route_registry": registry.canonical_object(),
        "typed_schema_registry": schemas.canonical_object(),
        "typed_route_manifest": route.canonical_object(),
        "route_identity_bundle": bundle.canonical_object(),
        "final_authorization": authorization.canonical_object(),
        "canonical_request_builder_identity": builder,
    }
    for name, value in values.items():
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    pool = _object(output / "candidate_pool.json")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K4_COMPONENT_BUNDLE_RECEIPT",
        "component_count": len(tuple(output.glob("*.json"))),
        "candidate_pool_hash": pool["pool_hash"],
        "route_registry_hash": registry.registry_hash,
        "route_manifest_hash": route.manifest_hash,
        "schema_registry_hash": schemas.registry_hash,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "final_authorization_hash": authorization.authorization_hash,
        "canonical_request_builder_hash": M336K4_FINAL_REQUEST_BUILDER_HASH,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    (output / "bundle_receipt.json").write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(receipt))


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K4 component input is not an object")
    return value


def _replace(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def _rehash_top_level(value: dict) -> dict:
    primary = tuple(
        name
        for name in (
            "authorization_hash",
            "receipt_hash",
            "manifest_hash",
            "registry_hash",
            "policy_hash",
            "contract_hash",
            "threshold_manifest_hash",
            "frozen_file_manifest_hash",
        )
        if name in value
    )
    if len(primary) > 1:
        raise M336K2ProtocolError("M336K4 component hash is ambiguous")
    if primary:
        field = primary[0]
        body = dict(value)
        body.pop(field)
        return {**body, field: content_hash(body)}
    return value


if __name__ == "__main__":
    main()
