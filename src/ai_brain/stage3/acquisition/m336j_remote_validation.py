"""Independent evaluation and installed-runtime checks for the M-33.6j route."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336i_evaluation import (
    M336IIndependentEvaluationRequest,
    _runtime_status,
    run_m336i_independent_java_evaluation,
)

_EVALUATION_CONFIG_FIELDS = {
    "route_manifest",
    "threshold_manifest",
    "windows_production_root",
    "karina_production_root",
    "semantic_goldens",
    "sealed_vault",
    "bindings",
    "candidate_pool",
    "qualification_report",
    "selected_manifest",
    "frozen_spdx_reference",
    "evaluator_ledger",
    "repository",
}


def run_m336j_remote_independent_evaluation(config_path: Path, output: Path) -> dict:
    """Run the existing independent evaluator from a strict private config."""

    config = strict_json_file(config_path.resolve(strict=True))
    if not isinstance(config, dict) or set(config) != _EVALUATION_CONFIG_FIELDS:
        raise ValueError("M336J remote evaluation config fields changed")
    repository = Path(config["repository"]).resolve(strict=True)
    windows = Path(config["windows_production_root"]).resolve(strict=True)
    karina = Path(config["karina_production_root"]).resolve(strict=True)
    request = M336IIndependentEvaluationRequest(
        route_manifest=Path(config["route_manifest"]),
        threshold_manifest=Path(config["threshold_manifest"]),
        windows_production_seal=windows / "m336i_production_seal.json",
        karina_production_seal=karina / "m336i_production_seal.json",
        windows_production_output=windows / "production_output.json",
        karina_production_output=karina / "production_output.json",
        windows_field_evidence_manifest=windows / "field_evidence_manifest.json",
        karina_field_evidence_manifest=karina / "field_evidence_manifest.json",
        public_candidate_pack=windows / "candidate_pack",
        windows_replay_receipt=windows / "sealed_source_replay_receipt.json",
        karina_replay_receipt=karina / "sealed_source_replay_receipt.json",
        independently_authored_semantic_goldens=Path(config["semantic_goldens"]),
        external_sealed_vault=Path(config["sealed_vault"]),
        source_entry_bindings=Path(config["bindings"]),
        candidate_pool=Path(config["candidate_pool"]),
        qualification_report=Path(config["qualification_report"]),
        selected_manifest=Path(config["selected_manifest"]),
        frozen_spdx_reference=Path(config["frozen_spdx_reference"]),
        evaluator_ledger=Path(config["evaluator_ledger"]),
        git_worktrees=(repository,),
    )
    result = run_m336i_independent_java_evaluation(request)
    if result.status != "PASS":
        raise ValueError("M336J remote independent evaluation failed")
    write_canonical_json(output, result)
    return asdict(result)


def run_m336j_installed_runtime(pack_root: Path) -> dict:
    """Load the source-free pack through the installed generic runtime."""

    pack = verify_java_public_candidate_pack(pack_root.resolve(strict=True))
    runtime_status = _runtime_status(pack_root)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_INSTALLED_RUNTIME",
        "candidate_pack_content_hash": pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": pack.candidate_pack_tree_hash,
        "runtime_status": runtime_status,
        "runtime_network_access_count": 0,
        "source_input_count": 0,
        "source_leak_count": 0,
        "status": runtime_status,
    }
    if runtime_status != "PASS":
        raise ValueError("M336J installed runtime failed")
    return {**body, "receipt_hash": content_hash(body)}


def run_m336j_remote_replay_and_pack_verification(
    pack_root: Path, replay_receipt: Path
) -> dict:
    """Independently bind sealed replay to the exact source-free public pack."""

    pack = verify_java_public_candidate_pack(pack_root.resolve(strict=True))
    replay = strict_json_file(replay_receipt.resolve(strict=True))
    if not isinstance(replay, dict):
        raise TypeError("M336J replay receipt must be an object")
    body = dict(replay)
    claimed = body.pop("receipt_hash", None)
    candidate_hash = replay.get(
        "candidate_pack_content_hash", replay.get("public_candidate_pack_content_hash")
    )
    if (
        content_hash(body) != claimed
        or replay.get("status") != "PASS"
        or candidate_hash != pack.candidate_pack_content_hash
    ):
        raise ValueError("M336J sealed replay/public pack binding changed")
    result = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_REPLAY_AND_PACK_VERIFICATION",
        "candidate_pack_content_hash": pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": pack.candidate_pack_tree_hash,
        "sealed_replay_receipt_hash": claimed,
        "source_input_count": 0,
        "source_leak_count": 0,
        "status": "PASS",
    }
    return {**result, "receipt_hash": content_hash(result)}
