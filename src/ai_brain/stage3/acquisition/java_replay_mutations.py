"""Executable fail-closed mutation battery for M-33.6 production replay."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_production_replay import (
    JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX,
    JAVA_PRODUCTION_REPLAY_FILENAME,
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.domains.aliases import ALIAS_SEMANTICS_DEPENDENCY_PREFIX
from ai_brain.stage3.domains.loader import load_pack


def run_m336_replay_mutation_battery(
    candidate_pack: Path,
    *,
    installed_pack_root: Path,
    provider_registry,
) -> dict[str, object]:
    """Prove each required authority layer rejects a content mutation."""

    results = []
    with tempfile.TemporaryDirectory(prefix="m336-replay-mutations-") as temporary:
        root = Path(temporary)
        closure_mutations = (
            (
                "raw_source",
                lambda row: row["raw_source_blobs"][0].__setitem__(1, "AA=="),
            ),
            (
                "canonical_source",
                lambda row: row["canonical_text_blobs"][0].__setitem__(1, "AA=="),
            ),
            (
                "source_relative_path",
                lambda row: row["source_paths"][0].__setitem__(0, "forged/Source.java"),
            ),
            (
                "document_id",
                lambda row: row["bundle"]["documents"][0].__setitem__(
                    "document_id", "document.forged"
                ),
            ),
            (
                "canonical_ordering",
                _mutate_canonical_ordering,
            ),
            (
                "java_identity",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "source_index_hash", "1" * 64
                ),
            ),
            (
                "module",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "source_index_hash", "2" * 64
                ),
            ),
            (
                "source_scope",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "proposal_manifest_hash", "3" * 64
                ),
            ),
            (
                "type_resolution_receipt",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "type_universe_manifest_hash", "4" * 64
                ),
            ),
            (
                "field_evidence",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "field_evidence_manifest_hash", "5" * 64
                ),
            ),
            (
                "packability_group",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "packability_report_hash", "6" * 64
                ),
            ),
            (
                "withholding_reason",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "packability_report_hash", "7" * 64
                ),
            ),
            (
                "trust_decision",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "trust_decision_manifest_hash", "8" * 64
                ),
            ),
            (
                "closure",
                lambda row: row["expected_production_artifacts"].__setitem__(
                    "trust_closure_hash", "9" * 64
                ),
            ),
            (
                "java_release",
                lambda row: row["release_identity"].__setitem__(
                    "policy_version", "forged.release"
                ),
            ),
        )
        for name, mutation in closure_mutations:
            target = root / name
            shutil.copytree(candidate_pack, target)
            row = _load(target / JAVA_PRODUCTION_REPLAY_FILENAME)
            mutation(row)
            _write(target / JAVA_PRODUCTION_REPLAY_FILENAME, row)
            _rehash_production_closure(target)
            results.append(_must_reject(name, target))

        for name, key in (
            ("exact_reference", "exact_references"),
            ("search_alias", "search_aliases"),
        ):
            target = root / name
            shutil.copytree(candidate_pack, target)
            alias_path = target / "alias_semantics.json"
            row = _load(alias_path)
            row[key][0]["record_id"] = "m336.unknown.record"
            _write(alias_path, row)
            _rehash_alias_semantics(target)
            results.append(_must_reject(name, target))

        candidate = root / "candidate_pack"
        shutil.copytree(candidate_pack, candidate)
        with (candidate / "knowledge.jsonl").open("ab") as stream:
            stream.write(b"{}\n")
        results.append(_must_reject("candidate_pack", candidate))

        installed_source = next(
            path
            for path in installed_pack_root.rglob("manifest.json")
            if "packs" in path.parts
        ).parent
        installed = root / "installed_pack"
        shutil.copytree(installed_source, installed)
        installed_manifest = _load(installed / "manifest.json")
        installed_manifest["canonical_name_en"] = "forged installed pack"
        _write(installed / "manifest.json", installed_manifest)
        results.append(_must_reject_load("installed_pack", installed))

        mutated_provider = replace(provider_registry, registry_hash="a" * 64)
        rejected = False
        error_type = None
        try:
            mutated_provider.verify()
        except (KeyError, OSError, TypeError, ValueError) as error:
            rejected = True
            error_type = type(error).__name__
        if not rejected:
            raise AssertionError("provider manifest mutation was accepted")
        results.append(
            {
                "mutation_id": "provider_manifest",
                "rejected": True,
                "error_type": error_type,
            }
        )

    body = {
        "schema_version": 1,
        "mutation_count": len(results),
        "rejected_count": sum(item["rejected"] for item in results),
        "mutations": tuple(results),
        "status": "PASS" if all(item["rejected"] for item in results) else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _must_reject(name: str, root: Path) -> dict[str, object]:
    try:
        verify_compiled_java_production_standalone(root)
    except (KeyError, OSError, TypeError, ValueError) as error:
        return {
            "mutation_id": name,
            "rejected": True,
            "error_type": type(error).__name__,
        }
    raise AssertionError(f"standalone production replay accepted mutation: {name}")


def _mutate_canonical_ordering(row) -> None:
    documents = row["bundle"]["documents"]
    if len(documents) > 1:
        documents.reverse()
    else:
        documents.append(dict(documents[0]))


def _must_reject_load(name: str, root: Path) -> dict[str, object]:
    try:
        load_pack(root)
    except (KeyError, OSError, TypeError, ValueError) as error:
        return {
            "mutation_id": name,
            "rejected": True,
            "error_type": type(error).__name__,
        }
    raise AssertionError(f"installed pack loader accepted mutation: {name}")


def _rehash_production_closure(root: Path) -> None:
    path = root / JAVA_PRODUCTION_REPLAY_FILENAME
    row = _load(path)
    row.pop("artifact_hash", None)
    artifact_hash = content_hash(row)
    _write(path, {**row, "artifact_hash": artifact_hash})
    _rehash_pack_dependency(
        root, JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX, artifact_hash
    )


def _rehash_alias_semantics(root: Path) -> None:
    path = root / "alias_semantics.json"
    row = _load(path)
    row.pop("index_hash", None)
    index_hash = content_hash(row)
    _write(path, {**row, "index_hash": index_hash})
    _rehash_pack_dependency(root, ALIAS_SEMANTICS_DEPENDENCY_PREFIX, index_hash)


def _rehash_pack_dependency(root: Path, prefix: str, digest: str) -> None:
    manifest_path = root / "manifest.json"
    manifest = _load(manifest_path)
    manifest["dependency_packs"] = [
        prefix + digest if item.startswith(prefix) else item
        for item in manifest["dependency_packs"]
    ]
    manifest.pop("pack_content_hash", None)
    pack_hash = content_hash(manifest)
    _write(manifest_path, {**manifest, "pack_content_hash": pack_hash})
    outer_path = root / "pack_manifest.json"
    outer = _load(outer_path)
    outer["pack_content_hash"] = pack_hash
    _write(outer_path, outer)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
