"""Build deterministic M-33.6a evidence from only the three disclosed candidates."""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

import tree_sitter_java
from tree_sitter import Language, Parser

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.maven_provenance import (
    canonical_source_bytes,
    correspond_source_trees,
    inspect_source_archive,
    license_text_evidence,
    maven_coordinate,
    parse_maven_pom,
    verify_sha256_sidecar,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    resolve_historical_license_evidence as resolve_license_evidence,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle

CANDIDATES = (
    {
        "id": "google-guava",
        "group": "com.google.guava",
        "artifact": "guava",
        "version": "33.4.8-jre",
        "archive": "google-guava-33.4.8-jre-sources.jar",
        "pom": "guava.pom",
        "scm_archive": "guava-scm.zip",
        "scm_repository": "https://github.com/google/guava.git",
        "scm_ref": "refs/tags/v33.4.8",
        "scm_commit": "f06690fa3e874f65515e8fd338a74d636e2c792f",
        "source_prefix": "guava/src/",
    },
    {
        "id": "apache-commons-collections4",
        "group": "org.apache.commons",
        "artifact": "commons-collections4",
        "version": "4.5.0",
        "archive": "apache-commons-collections4-4.5.0-sources.jar",
        "pom": "commons.pom",
        "scm_archive": "commons-scm.zip",
        "scm_repository": "https://github.com/apache/commons-collections.git",
        "scm_ref": "refs/tags/rel/commons-collections-4.5.0",
        "scm_commit": "7f7fb0244abc940a2e9dd28b67508c0483a58c3e",
        "source_prefix": "src/main/java/",
    },
    {
        "id": "caffeine",
        "group": "com.github.ben-manes.caffeine",
        "artifact": "caffeine",
        "version": "3.2.0",
        "archive": "caffeine-3.2.0-sources.jar",
        "pom": "caffeine.pom",
        "scm_archive": "caffeine-scm.zip",
        "scm_repository": "https://github.com/ben-manes/caffeine.git",
        "scm_ref": "refs/tags/v3.2.0",
        "scm_commit": "93d845e58d8e7bf2dfc88a31c5a078bca5bf4dbf",
        "source_prefix": "caffeine/src/main/java/",
    },
)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _scm_contents(path: Path):
    java = []
    licenses = []
    with zipfile.ZipFile(path) as opened:
        for info in opened.infolist():
            parts = info.filename.split("/", 1)
            if len(parts) != 2 or info.is_dir():
                continue
            relative = parts[1]
            raw = opened.read(info)
            if relative.endswith(".java"):
                java.append((relative, raw))
            if relative in {"LICENSE", "LICENSE.txt"}:
                licenses.append((relative, raw))
    return tuple(java), tuple(licenses)


def build(historical_root: Path, metadata_root: Path):
    archive_root = historical_root / "archives"
    extracted_root = historical_root / "roots"
    rows = []
    raw_hashes = set()
    canonical_hashes = set()
    paths = []
    for spec in CANDIDATES:
        coordinate = maven_coordinate(
            group_id=spec["group"],
            artifact_id=spec["artifact"],
            version=spec["version"],
        )
        archive_path = archive_root / spec["archive"]
        archive_raw = archive_path.read_bytes()
        inspection = inspect_source_archive(archive_raw)
        pom_raw = (metadata_root / spec["pom"]).read_bytes()
        pom = parse_maven_pom(pom_raw, coordinate)
        scm_java, scm_licenses = _scm_contents(metadata_root / spec["scm_archive"])
        correspondence = correspond_source_trees(
            inspection.java_entries,
            scm_java,
            repository_path_prefixes=(spec["source_prefix"],),
        )
        root_license = next(
            (
                (name, raw)
                for name, raw in scm_licenses
                if name in {"LICENSE", "LICENSE.txt"}
            ),
            None,
        )
        scm_license = license_text_evidence(*root_license) if root_license else None
        mode, license_status, conflicts = resolve_license_evidence(
            pom_claims=pom.licenses,
            embedded_texts=inspection.license_evidence,
            scm_text=scm_license,
            immutable_scm_verified=True,
            correspondence=correspondence,
        )
        for relative, raw in inspection.java_entries:
            raw_hashes.add(bytes_hash(raw))
            canonical_hashes.add(bytes_hash(canonical_source_bytes(raw)))
            paths.append(f"{spec['id']}/{relative}")
        sidecar_prefix = {
            "google-guava": "guava",
            "apache-commons-collections4": "commons",
            "caffeine": "caffeine",
        }[spec["id"]]
        jar_sidecar = metadata_root / f"{sidecar_prefix}.jar.sha256"
        pom_sidecar = metadata_root / f"{sidecar_prefix}.pom.sha256"
        sidecars = {}
        for label, payload, sidecar in (
            ("sources_jar", archive_raw, jar_sidecar),
            ("pom", pom_raw, pom_sidecar),
        ):
            if sidecar.exists():
                verify_sha256_sidecar(payload, sidecar.read_bytes())
                sidecars[label] = "VERIFIED"
            else:
                sidecars[label] = "NOT_PUBLISHED"
        signature_prefix = sidecar_prefix
        signature_hashes = tuple(
            bytes_hash(path.read_bytes())
            for path in (
                metadata_root / f"{signature_prefix}-sources-jar-asc",
                metadata_root / f"{signature_prefix}-pom-asc",
            )
            if path.exists()
        )
        scm_tree_rows = tuple(
            (path, bytes_hash(canonical_source_bytes(raw)))
            for path, raw in sorted(scm_java)
        )
        row = {
            "candidate_id": spec["id"],
            "coordinate": f"{spec['group']}:{spec['artifact']}:{spec['version']}",
            "source_archive_url": f"{coordinate.repository}/{coordinate.canonical_repository_path}",
            "source_archive_size": len(archive_raw),
            "source_archive_sha256": bytes_hash(archive_raw),
            "source_archive_entry_count": inspection.entry_count,
            "java_entry_count": len(inspection.java_entries),
            "embedded_license_paths": tuple(
                item.evidence_path for item in inspection.license_evidence
            ),
            "pom_sha256": pom.pom_sha256,
            "pom_license_declarations": tuple(
                item.spdx_identifier for item in pom.licenses
            ),
            "pom_scm_connection": pom.scm_connection,
            "pom_scm_url": pom.scm_url,
            "sha256_sidecars": sidecars,
            "detached_signature_hashes": signature_hashes,
            "scm_repository": spec["scm_repository"],
            "scm_ref": spec["scm_ref"],
            "scm_commit": spec["scm_commit"],
            "upstream_license_path": scm_license.evidence_path if scm_license else None,
            "upstream_license_sha256": scm_license.raw_text_sha256
            if scm_license
            else None,
            "normalized_source_tree_hash": content_hash(scm_tree_rows),
            "source_jar_tree_hash": inspection.archive_tree_hash,
            "correspondence_hash": correspondence.correspondence_hash,
            "exact_match_count": correspondence.exact_match_count,
            "relocated_match_count": correspondence.relocated_match_count,
            "unmatched_count": correspondence.unmatched_count,
            "ambiguous_match_count": correspondence.ambiguous_count,
            "license_evidence_mode": mode,
            "intrinsic_license_status": license_status,
            "conflicts": conflicts,
            "future_qualification_status": "DENYLISTED",
        }
        qualification_body = {
            "schema_version": 1,
            "candidate_id": spec["id"],
            "coordinate": row["coordinate"],
            "requirement": "OPTIONAL",
            "intrinsic_status": "ELIGIBLE",
            "future_status": "DENYLISTED",
            "license_evidence_mode": mode,
            "complete_evidence": license_status == "VERIFIED"
            and correspondence.unmatched_count == 0
            and correspondence.ambiguous_count == 0,
            "eligible_root": None,
            "reasons": ("PERMANENT_DISCLOSED_MATERIAL_DENYLIST",),
        }
        row["qualification_receipt"] = {
            **qualification_body,
            "receipt_hash": content_hash(qualification_body),
        }
        rows.append(row)

    parser = Parser(Language(tree_sitter_java.language()))
    java_paths = tuple(
        path
        for path in sorted(extracted_root.rglob("*.java"))
        if not parser.parse(path.read_bytes(), encoding="utf8").root_node.has_error
    )
    declarations = []
    with tempfile.TemporaryDirectory(prefix="m336a-denylist-index-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        for batch_index, offset in enumerate(range(0, len(java_paths), 200)):
            bundle = ingest_bundle(
                java_paths[offset : offset + 200],
                bundle_id=f"m336a-disclosed-development-{batch_index:02d}",
                domain_tags=("java-api",),
                imported_at="2026-09-04T00:00:00Z",
                store=store,
                source_root=extracted_root,
            )
            declarations.extend(index_java_bundle(bundle, store).declarations)
    fingerprints = {
        content_hash(
            (
                item.receiver_type,
                item.member_kind,
                item.member_name,
                item.canonical_source_signature,
                item.erased_jvm_descriptor,
            )
        )
        for item in declarations
        if item.member_kind in {"method", "constructor"}
    }
    denylist_body = {
        "schema_version": 1,
        "classification": "DISCLOSED_DEVELOPMENT_REGRESSION_ONLY",
        "coordinates": tuple(sorted(row["coordinate"] for row in rows)),
        "source_archive_urls": tuple(sorted(row["source_archive_url"] for row in rows)),
        "archive_hashes": tuple(sorted(row["source_archive_sha256"] for row in rows)),
        "pom_hashes": tuple(sorted(row["pom_sha256"] for row in rows)),
        "raw_source_hashes": tuple(sorted(raw_hashes)),
        "canonical_text_hashes": tuple(sorted(canonical_hashes)),
        "source_tree_hashes": tuple(
            sorted(row["normalized_source_tree_hash"] for row in rows)
        ),
        "selected_path_manifest_hashes": (content_hash(tuple(sorted(paths))),),
        "declaration_fingerprints": tuple(sorted(fingerprints)),
        "scm_revision_hashes": tuple(sorted(row["scm_commit"] for row in rows)),
        "correspondence_hashes": tuple(
            sorted(row["correspondence_hash"] for row in rows)
        ),
    }
    denylist = {**denylist_body, "manifest_hash": content_hash(denylist_body)}
    matrix_body = {
        "schema_version": 1,
        "candidate_count": len(rows),
        "candidates": tuple(rows),
        "all_candidates_intrinsically_verified": all(
            row["intrinsic_license_status"] == "VERIFIED" for row in rows
        ),
        "future_eligible_candidate_count": 0,
        "new_untouched_corpus_acquired": False,
    }
    matrix = {**matrix_body, "matrix_hash": content_hash(matrix_body)}
    return denylist, matrix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--denylist-output", type=Path, required=True)
    parser.add_argument("--snapshot-output", type=Path, required=True)
    args = parser.parse_args()
    denylist, matrix = build(args.historical_root, args.metadata_root)
    _write(args.denylist_output, denylist)
    _write(args.snapshot_output, matrix)


if __name__ == "__main__":
    main()
