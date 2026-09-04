"""Fresh-process replay for oracle-free Java production trust."""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_compilation_identity import (
    JAVA_SEMANTIC_COMPILATION_EPOCH,
)
from ai_brain.stage3.acquisition.java_production import (
    JavaProductionTrustBatch,
    run_java_acquisition_pipeline,
)
from ai_brain.stage3.acquisition.java_release import (
    JavaReleaseIdentity,
    verify_java_release_identity,
)
from ai_brain.stage3.acquisition.models import AcquisitionManifest, SourceBundle
from ai_brain.stage3.acquisition.persistence import AcquisitionStore, _document
from ai_brain.stage3.domains.aliases import ALIAS_SEMANTICS_DEPENDENCY_PREFIX
from ai_brain.stage3.domains.loader import load_pack

JAVA_PRODUCTION_REPLAY_SCHEMA_VERSION = 1
JAVA_PRODUCTION_REPLAY_FILENAME = "java_production_closure.json"
JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX = "java-production-closure."


def build_java_production_replay_artifact(batch, store, source_bindings):
    documents = tuple(
        sorted(batch.bundle.documents, key=lambda item: item.relative_path)
    )
    raw_hashes = tuple(sorted({item.bytes_hash for item in documents}))
    canonical_hashes = tuple(sorted({item.canonical_text_hash for item in documents}))
    raw_blobs = tuple(
        (digest, base64.b64encode(store.get_blob(digest)).decode("ascii"))
        for digest in raw_hashes
    )
    canonical_blobs = tuple(
        (digest, base64.b64encode(store.get_blob(digest)).decode("ascii"))
        for digest in canonical_hashes
    )
    expected = _expected_artifacts(batch)
    body = {
        "schema_version": JAVA_PRODUCTION_REPLAY_SCHEMA_VERSION,
        "deterministic_run_id": batch.closure.deterministic_run_id,
        "bundle": _semantic_bundle(batch.bundle),
        "raw_source_blobs": raw_blobs,
        "canonical_text_blobs": canonical_blobs,
        "source_paths": tuple(
            (item.relative_path, item.bytes_hash, item.canonical_text_hash)
            for item in documents
        ),
        "release_identity": asdict(batch.release_identity),
        "expected_production_artifacts": expected,
        "expected_production_artifacts_hash": content_hash(expected),
        "parser_common_artifact": asdict(batch.parser_common_artifact),
        "compiled_source_bindings": tuple(asdict(item) for item in source_bindings),
    }
    return {**body, "artifact_hash": content_hash(body)}


def _semantic_bundle(bundle):
    """Serialize replay semantics without acquisition-event timestamps."""

    row = asdict(bundle)
    row["created_at"] = JAVA_SEMANTIC_COMPILATION_EPOCH
    row["documents"] = tuple(
        {**document, "imported_at": JAVA_SEMANTIC_COMPILATION_EPOCH}
        for document in row["documents"]
    )
    return row


def verify_compiled_java_production_standalone(pack_root: Path) -> dict[str, object]:
    pack = load_pack(pack_root)
    path = pack_root / JAVA_PRODUCTION_REPLAY_FILENAME
    row = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict)
    claimed = row.pop("artifact_hash")
    if content_hash(row) != claimed:
        raise ValueError("Java production replay artifact hash mismatch")
    replay_dependencies = tuple(
        item
        for item in pack.manifest.dependency_packs
        if item.startswith(JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX)
    )
    other_dependencies = tuple(
        item
        for item in pack.manifest.dependency_packs
        if item.startswith(ALIAS_SEMANTICS_DEPENDENCY_PREFIX)
    )
    if replay_dependencies != (JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX + claimed,) or (
        pack.alias_semantics is None
    ) != (not other_dependencies):
        raise ValueError("pack does not bind exact Java production replay artifact")
    if row["schema_version"] != JAVA_PRODUCTION_REPLAY_SCHEMA_VERSION:
        raise ValueError("unsupported Java production replay schema")
    _verify_source_closure(row)
    expected = row["expected_production_artifacts"]
    if content_hash(expected) != row["expected_production_artifacts_hash"]:
        raise ValueError("production replay expected-artifact hash mismatch")
    release = JavaReleaseIdentity(**row["release_identity"])
    verify_java_release_identity(release)
    with tempfile.TemporaryDirectory(prefix="m344-production-replay-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        for digest, encoded in (
            *row["raw_source_blobs"],
            *row["canonical_text_blobs"],
        ):
            store.put_blob(
                base64.b64decode(encoded, validate=True), expected_hash=digest
            )
        batch = run_java_acquisition_pipeline(
            _bundle(row["bundle"]),
            store,
            deterministic_run_id=row["deterministic_run_id"],
            release_identity=release,
        )
    if _expected_artifacts(batch) != expected:
        raise ValueError("standalone Java production replay mismatch")
    if canonical_json(asdict(batch.parser_common_artifact)) != canonical_json(
        row["parser_common_artifact"]
    ):
        raise ValueError("standalone Java parser artifact mismatch")
    if canonical_json(asdict(batch.release_identity)) != canonical_json(
        row["release_identity"]
    ):
        raise ValueError("standalone Java release identity mismatch")
    if canonical_json(
        [asdict(item) for item in pack.source_bindings]
    ) != canonical_json(row["compiled_source_bindings"]):
        raise ValueError("standalone Java source bindings mismatch")
    return {
        "status": "PASS",
        "artifact_hash": claimed,
        "trusted_proposal_count": batch.trusted_count,
        "authorization_count": batch.trusted_count,
        "evidence_count": batch.field_evidence.evidence_count,
        "raw_source_blob_count": len(row["raw_source_blobs"]),
        "canonical_text_blob_count": len(row["canonical_text_blobs"]),
    }


def _expected_artifacts(batch: JavaProductionTrustBatch) -> dict[str, object]:
    return {
        "trust_closure_hash": batch.closure.closure_hash,
        "field_evidence_manifest_hash": batch.field_evidence.manifest_hash,
        "evidence_policy_manifest_hash": batch.evidence_policy.manifest_hash,
        "evidence_transformation_registry_hash": batch.field_evidence.transformation_registry_hash,
        "source_index_hash": batch.source_index.index_hash,
        "type_universe_manifest_hash": batch.source_index.type_universe_manifest_hash,
        "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
        "proposal_batch_hash": batch.proposal_batch.batch_hash,
        "proposal_field_manifest_hash": batch.proposal_batch.proposal_field_manifest_hash,
        "trust_decision_manifest_hash": batch.closure.trust_decision_manifest_hash,
        "trusted_proposal_manifest_hash": batch.closure.trusted_proposal_manifest_hash,
        "packability_report_hash": batch.packability_report.report_hash,
        "release_identity_hash": batch.release_identity.identity_hash,
    }


def _verify_source_closure(row) -> None:
    paths = sorted(
        (item["relative_path"], item["bytes_hash"], item["canonical_text_hash"])
        for item in row["bundle"]["documents"]
    )
    if row["source_paths"] != [list(item) for item in paths]:
        raise ValueError("production replay source path closure mismatch")
    raw_hashes = [item[0] for item in row["raw_source_blobs"]]
    canonical_hashes = [item[0] for item in row["canonical_text_blobs"]]
    if set(raw_hashes) != {item[1] for item in paths} or set(canonical_hashes) != {
        item[2] for item in paths
    }:
        raise ValueError("production replay source denominator mismatch")
    for digest, encoded in (*row["raw_source_blobs"], *row["canonical_text_blobs"]):
        if bytes_hash(base64.b64decode(encoded, validate=True)) != digest:
            raise ValueError("production replay source blob bytes mismatch")


def _bundle(row):
    documents = tuple(_document(item) for item in row["documents"])
    manifest_row = row["manifest"]
    manifest = AcquisitionManifest(
        **{**manifest_row, "document_hashes": tuple(manifest_row["document_hashes"])}
    )
    return SourceBundle(
        **{
            **row,
            "domain_tags": tuple(row["domain_tags"]),
            "documents": documents,
            "manifest": manifest,
        }
    )


def _strict(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in Java production replay artifact")
        result[key] = value
    return result
