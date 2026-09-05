from __future__ import annotations

import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    DEFAULT_REGISTRY_ROOT,
    append_disclosed_java_entries_v2,
    build_disclosed_java_material_entry,
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
    verify_disclosure_registry_append_receipt,
)
from ai_brain.stage3.acquisition.java_evidence_policy import (
    load_production_java_evidence_policy,
)
from ai_brain.stage3.acquisition.m336e_authority import (
    M336E_AUTHORITY_ID,
    M336E_AUTHORITY_STATEMENT_SHA256,
    M336ESourceAuthorizationBinding,
    load_m336e_authority_registry,
    m336e_receipt_from_dict,
    m336e_receipt_public_dict,
)
from ai_brain.stage3.acquisition.m336e_comparison import (
    compare_m336e_production_trees,
)
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    ProducerContractCompatibilityGate,
    PublicArtifactProducer,
    canonical_public_json,
    m336e_future_public_producers,
    produce_m336e_acquisition_receipts,
    produce_m336e_qualification_summary,
)
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    _production_index_candidate,
)
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    _apply_fresh_scoped_qualification,
    run_fresh_acquisition_and_preflight,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    CanonicalVaultPath,
    build_portable_vault_manifest,
    build_source_entry_binding,
    build_source_entry_binding_manifest,
    build_source_entry_id,
    canonical_vault_paths,
    portable_vault_manifest_from_dict,
    source_entry_binding_manifest_from_dict,
    verify_portable_vault_manifest,
)
from ai_brain.stage3.acquisition.m336e_metadata_pool import (
    build_m336e_disclosed_identity_denylist,
    fresh_metadata_candidate_seeds,
    probe_metadata_pool_v4,
    scan_m336e_local_cache_names,
    validate_metadata_pool_v4,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336e_selectability import (
    build_selectable_source_census,
    build_selectable_source_decision,
    prove_selector_feasibility,
    select_final_sources_once,
    selectable_source_census_from_dict,
    selected_source_manifest_from_dict,
    selector_feasibility_proof_from_dict,
    selector_receipt_from_dict,
    verify_selector_result_without_invocation,
)


def _identity(root: str, index: int):
    raw = content_hash((root, index, "raw"))
    return build_source_entry_id(
        candidate_family_id=root,
        source_jar_sha256=content_hash((root, "jar")),
        archive_relative_path=f"org/example/{root}/C{index:03d}.java",
        raw_source_sha256=raw,
        canonical_source_sha256=content_hash((root, index, "canonical")),
    )


def test_m336e_production_comparison_excludes_only_host_bound_receipts(
    tmp_path: Path,
):
    windows = tmp_path / "windows"
    karina = tmp_path / "karina"
    windows.mkdir()
    karina.mkdir()
    for root in (windows, karina):
        (root / "production_output.json").write_text(
            canonical_json({"semantic": "identical"}) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    (windows / "m336e_production_execution.json").write_text(
        canonical_json({"platform": "windows", "seal_hash": "a" * 64}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (karina / "m336e_production_execution.json").write_text(
        canonical_json({"platform": "karina", "seal_hash": "b" * 64}) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    report = compare_m336e_production_trees(windows, karina)

    assert report["status"] == "PASS"
    assert report["platform_independent_difference_count"] == 0
    assert report["host_bound_artifacts"] == ("m336e_production_execution.json",)

    (karina / "production_output.json").write_text(
        canonical_json({"semantic": "different"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    failed = compare_m336e_production_trees(windows, karina)
    assert failed["status"] == "FAIL"
    assert failed["different_paths"] == ("production_output.json",)


def _selectable(root: str, index: int, *, constructs=("class", "method")):
    identity = _identity(root, index)
    return build_selectable_source_decision(
        source_entry_id=identity,
        candidate_root=root,
        canonical_path=f"{root}/org/example/{root}/C{index:03d}.java",
        analysis_eligible=True,
        publication_allowed=True,
        source_use_receipt_valid=True,
        scoped_license_resolved=True,
        scm_correspondence_complete=True,
        parser_status="PASS",
        declaration_count=3,
        callable_declaration_count=2,
        supported_callable_declaration_count=2,
        construct_classes=constructs,
        evidence_policy_path_declared=True,
    )


def _binding(decision):
    identity = decision.source_entry_id
    archive = identity.canonical_archive_relative_path
    return build_source_entry_binding(
        source_entry_id=identity,
        archive_path=archive,
        scm_path=f"src/main/java/{archive}",
        vault_path=f"candidates/{decision.candidate_root}/sources/{archive}",
        selected_path=f"{decision.candidate_root}/{archive}",
        production_document_identity=f"document.{identity.identity_hash}",
    )


def _protocol_context(census_hash: str):
    return {
        "f20_sha": "1" * 40,
        "acquisition_run_id": "m336e.disclosed.integration-test.v1",
        "candidate_pool_hash": "2" * 64,
        "vault_tree_hash": "3" * 64,
        "qualification_manifest_hash": "4" * 64,
        "selectability_census_hash": census_hash,
    }


def _advance_to_census(ledger: RunProtocolLedger, context) -> None:
    early = {
        "f20_sha": context["f20_sha"],
        "acquisition_run_id": context["acquisition_run_id"],
        "candidate_pool_hash": context["candidate_pool_hash"],
    }
    ledger.append("FREEZE_VERIFIED", **early)
    ledger.append("ACQUISITION_RESERVED", **early)
    ledger.append("ACQUISITION_COMPLETED", **early)
    ledger.append(
        "VAULT_SEALED", **{**early, "vault_tree_hash": context["vault_tree_hash"]}
    )
    ledger.append(
        "QUALIFICATION_COMPLETED",
        **{
            **early,
            "vault_tree_hash": context["vault_tree_hash"],
            "qualification_manifest_hash": context["qualification_manifest_hash"],
        },
    )
    ledger.append("SELECTABILITY_CENSUS_COMPLETED", **context)


def test_canonical_vault_path_and_portable_manifest_are_host_independent(tmp_path):
    assert str(CanonicalVaultPath.parse("a\\б\\😀.java")) == "a/б/😀.java"
    assert str(CanonicalVaultPath.parse("e\u0301/C.java")) == "é/C.java"
    ordered = canonical_vault_paths(
        ("prefix.java", "prefix/deep/C.java", "кириллица/C.java", "emoji/😀.java")
    )
    assert ordered == tuple(sorted(ordered, key=lambda item: item.order_key))
    for rejected in ("", "/abs", "C:/drive", "a//b", "a/./b", "a/../b", "a\x00b"):
        with pytest.raises(ValueError):
            CanonicalVaultPath.parse(rejected)
    with pytest.raises(ValueError, match="NFC"):
        canonical_vault_paths(("é/C.java", "e\u0301/C.java"))
    with pytest.raises(ValueError, match="casefold"):
        canonical_vault_paths(("Root/C.java", "root/c.java"))

    vault = tmp_path / "vault"
    values = {
        "ascii/C.java": b"class C {}\n",
        "кириллица/Б.java": "class Б {}\n".encode(),
        "emoji/😀.java": b"class Smile {}\n",
        "prefix.java": b"same\n",
        "prefix/deep/deeper/value.txt": b"same\n",
    }
    for relative, raw in values.items():
        path = vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    manifest = build_portable_vault_manifest(vault)
    verify_portable_vault_manifest(vault, manifest)
    transferred = portable_vault_manifest_from_dict(
        json.loads(canonical_json(asdict(manifest)))
    )
    verify_portable_vault_manifest(vault, transferred)
    assert transferred == manifest
    assert manifest.file_count == len(values)
    assert tuple(row.canonical_path for row in manifest.rows) == tuple(
        sorted(values, key=lambda value: value.encode("utf-8"))
    )
    (vault / "ascii/C.java").write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="differs"):
        verify_portable_vault_manifest(vault, manifest)


def test_source_entry_identity_closes_every_path_domain_and_rejects_collisions():
    first = _selectable("alpha", 1)
    second = _selectable("beta", 2)
    manifest = build_source_entry_binding_manifest((_binding(first), _binding(second)))
    assert manifest.binding_count == 2
    with pytest.raises(ValueError, match="duplicate binding"):
        build_source_entry_binding_manifest((_binding(first), _binding(first)))
    collision = replace(
        _binding(second),
        selected_path=_binding(first).selected_path.upper(),
    )
    collision_body = asdict(collision)
    collision_body.pop("binding_hash")
    collision = replace(collision, binding_hash=content_hash(collision_body))
    with pytest.raises(ValueError, match="casefold"):
        build_source_entry_binding_manifest((_binding(first), collision))
    # Archive paths are scoped by source artifact, so conventional duplicate
    # paths in unrelated roots are valid while their global vault paths differ.
    other_identity = build_source_entry_id(
        candidate_family_id="gamma",
        source_jar_sha256="1" * 64,
        archive_relative_path=first.source_entry_id.canonical_archive_relative_path,
        raw_source_sha256="2" * 64,
        canonical_source_sha256="3" * 64,
    )
    other = build_source_entry_binding(
        source_entry_id=other_identity,
        archive_path=other_identity.canonical_archive_relative_path,
        scm_path=f"src/{other_identity.canonical_archive_relative_path}",
        vault_path=f"candidates/gamma/sources/{other_identity.canonical_archive_relative_path}",
        selected_path=f"gamma/{other_identity.canonical_archive_relative_path}",
        production_document_identity=f"document.{other_identity.identity_hash}",
    )
    assert (
        build_source_entry_binding_manifest((_binding(first), other)).binding_count == 2
    )


def test_census_proves_exact_capacity_before_persistent_selector_reservation(tmp_path):
    decisions = tuple(
        _selectable(
            root,
            index,
            constructs=("class", "method", "constructor")
            if index < 15
            else ("class", "method"),
        )
        for root in ("alpha", "beta", "gamma")
        for index in range(60)
    )
    census = build_selectable_source_census(decisions)
    proof = prove_selector_feasibility(
        census,
        construct_quotas=(("constructor", 30), ("method", 120)),
    )
    assert proof.hard_requirements_satisfied
    assert proof.selectable_root_count == 3
    assert proof.selectable_file_count == 180
    assert proof.balanced_capacity == 180
    bindings = build_source_entry_binding_manifest(_binding(item) for item in decisions)
    ledger = RunProtocolLedger(tmp_path / "ledger.jsonl", git_worktrees=(Path.cwd(),))
    context = _protocol_context(census.census_hash)
    _advance_to_census(ledger, context)
    selected, receipt = select_final_sources_once(
        census,
        proof,
        bindings,
        ledger,
        selector_seed="m336e-test-seed",
        **context,
    )
    assert selected.file_count == 180
    assert selected.root_count == 3
    assert max(count for _root, count in selected.root_distribution) <= 63
    assert receipt.selector_invocation_count == 1
    assert receipt.selector_rerun_count == 0
    assert ledger.receipt().selector_invocation_count == 1
    restarted = RunProtocolLedger(ledger.path, git_worktrees=(Path.cwd(),))
    with pytest.raises(ValueError, match="out of order"):
        restarted.append("SELECTOR_INVOCATION_RESERVED", **context)


def test_remote_host_verifies_selector_result_without_a_second_invocation(tmp_path):
    decisions = tuple(
        _selectable(
            root,
            index,
            constructs=("class", "method", "constructor")
            if index < 15
            else ("class", "method"),
        )
        for root in ("alpha", "beta", "gamma")
        for index in range(60)
    )
    census = build_selectable_source_census(decisions)
    proof = prove_selector_feasibility(
        census,
        construct_quotas=(("constructor", 30), ("method", 120)),
    )
    bindings = build_source_entry_binding_manifest(_binding(item) for item in decisions)
    ledger = RunProtocolLedger(tmp_path / "ledger.jsonl", git_worktrees=(Path.cwd(),))
    context = _protocol_context(census.census_hash)
    _advance_to_census(ledger, context)
    selected, receipt = select_final_sources_once(
        census,
        proof,
        bindings,
        ledger,
        selector_seed="m336e-test-seed",
        **context,
    )

    # Exercise the exact JSON transfer/deserialization boundary used by Karina.
    transferred_bindings = source_entry_binding_manifest_from_dict(
        json.loads(canonical_json(asdict(bindings)))
    )
    transferred_census = selectable_source_census_from_dict(
        json.loads(canonical_json(asdict(census)))
    )
    transferred_proof = selector_feasibility_proof_from_dict(
        json.loads(canonical_json(asdict(proof))), transferred_census
    )
    transferred_selected = selected_source_manifest_from_dict(
        json.loads(canonical_json(asdict(selected)))
    )
    transferred_receipt = selector_receipt_from_dict(
        json.loads(canonical_json(asdict(receipt)))
    )
    verify_selector_result_without_invocation(
        transferred_census,
        transferred_proof,
        transferred_bindings,
        transferred_selected,
        transferred_receipt,
    )
    assert ledger.receipt().selector_invocation_count == 1

    forged_row = replace(
        transferred_selected.files[0],
        selected_path="wrong/path.java",
    )
    forged = replace(
        transferred_selected,
        files=(forged_row, *transferred_selected.files[1:]),
    )
    with pytest.raises(ValueError, match="not bound"):
        verify_selector_result_without_invocation(
            transferred_census,
            transferred_proof,
            transferred_bindings,
            forged,
            transferred_receipt,
        )


def test_infeasible_census_leaves_selector_reservation_and_invocation_at_zero(tmp_path):
    decisions = tuple(
        _selectable(root, index) for root in ("alpha", "beta") for index in range(90)
    )
    census = build_selectable_source_census(decisions)
    proof = prove_selector_feasibility(census)
    assert not proof.hard_requirements_satisfied
    ledger = RunProtocolLedger(tmp_path / "ledger.jsonl", git_worktrees=(Path.cwd(),))
    context = _protocol_context(census.census_hash)
    _advance_to_census(ledger, context)
    with pytest.raises(ValueError, match="infeasible"):
        select_final_sources_once(
            census,
            proof,
            build_source_entry_binding_manifest(_binding(item) for item in decisions),
            ledger,
            selector_seed="m336e-test-seed",
            **context,
        )
    receipt = ledger.receipt()
    assert receipt.selector_invocation_count == 0
    assert receipt.selector_rerun_count == 0
    assert receipt.final_event_type == "SELECTABILITY_CENSUS_COMPLETED"


def test_protocol_mutation_invalidates_the_hash_chained_suffix(tmp_path):
    ledger = RunProtocolLedger(tmp_path / "ledger.jsonl", git_worktrees=(Path.cwd(),))
    context = _protocol_context("5" * 64)
    _advance_to_census(ledger, context)
    lines = ledger.path.read_bytes().splitlines(keepends=True)
    value = json.loads(lines[0])
    value["candidate_pool_hash"] = "9" * 64
    lines[0] = (canonical_json(value) + "\n").encode()
    ledger.path.write_bytes(b"".join(lines))
    with pytest.raises(ValueError):
        RunProtocolLedger(ledger.path, git_worktrees=(Path.cwd(),)).events()


def test_m336e_authority_root_is_exact_and_receipts_bind_f20(tmp_path):
    raw = (
        b"M336E_USER_AUTHORITY_V1\n"
        b"source_use=PRIVATE_LOCAL_ANALYSIS,LOCAL_RESEARCH_EVALUATION,"
        b"DERIVED_KNOWLEDGE_ONLY,RAW_SOURCE_RETENTION,"
        b"PUBLIC_REPRODUCIBLE_EVALUATION\n"
        b"publication_allow=DERIVED_PACK_PUBLICATION,METRICS_ONLY_PUBLICATION\n"
        b"publication_deny=RAW_SOURCE_PUBLICATION,SOURCE_EXCERPT_PUBLICATION\n"
        b"raw_storage=LOCAL_SEALED_VAULT_ONLY\n"
        b"authority_may_narrow=true\n"
        b"authority_may_widen=false\n"
    )
    statement = tmp_path / "authority.txt"
    statement.write_bytes(raw)
    assert bytes_hash(raw) == M336E_AUTHORITY_STATEMENT_SHA256
    registry = load_m336e_authority_registry(
        statement, expected_statement_sha256=M336E_AUTHORITY_STATEMENT_SHA256
    )
    assert registry.root.authority_id == M336E_AUTHORITY_ID
    binding = M336ESourceAuthorizationBinding(
        f20_sha="1" * 40,
        acquisition_run_id="m336e.test.acquisition",
        candidate_family_id="candidate",
        maven_coordinate="org.example:candidate:1",
        source_repository_url="https://repo.maven.apache.org/example-sources.jar",
        source_jar_sha256="2" * 64,
        pom_sha256="3" * 64,
        immutable_scm_commit="4" * 40,
        scm_archive_sha256="5" * 64,
        source_tree_hash="6" * 64,
        local_vault_manifest_hash="7" * 64,
    )
    receipt = registry.issue(binding)
    registry.verify(receipt, expected_binding=binding)
    transferred = m336e_receipt_from_dict(m336e_receipt_public_dict(receipt))
    independent_registry = load_m336e_authority_registry(
        statement, expected_statement_sha256=M336E_AUTHORITY_STATEMENT_SHA256
    )
    independent_registry.verify(transferred, expected_binding=binding)
    with pytest.raises(ValueError, match="binding mismatch"):
        independent_registry.verify(
            transferred,
            expected_binding=replace(binding, f20_sha="9" * 40),
        )
    with pytest.raises(ValueError, match="sole frozen"):
        load_m336e_authority_registry(statement, expected_statement_sha256="8" * 64)
    statement.write_bytes(raw.replace(b"M336E", b"M336D", 1))
    with pytest.raises(ValueError, match="byte hash differs"):
        load_m336e_authority_registry(
            statement, expected_statement_sha256=M336E_AUTHORITY_STATEMENT_SHA256
        )


def test_fresh_metadata_v4_seeds_exclude_all_disclosed_identity_classes():
    seeds = fresh_metadata_candidate_seeds()
    denylist = build_m336e_disclosed_identity_denylist()
    assert len(seeds) >= 48
    assert len({item.organization_id for item in seeds}) >= 40
    assert (
        max(
            sum(other.organization_id == item.organization_id for other in seeds)
            for item in seeds
        )
        <= 2
    )
    assert not (
        {item.family_id for item in seeds} & set(denylist["excluded_family_ids"])
    )
    assert not (
        {f"{item.group_id}:{item.artifact_id}:{item.version}" for item in seeds}
        & set(denylist["excluded_coordinates"])
    )
    assert not (
        {item.scm_repository for item in seeds}
        & set(denylist["excluded_scm_repositories"])
    )
    assert denylist["registry_entry_count"] == 30


def test_fresh_metadata_v4_cache_census_never_reads_candidate_bodies(
    tmp_path, monkeypatch
):
    seed = fresh_metadata_candidate_seeds()[0]
    cache = tmp_path / "cache"
    cache.mkdir()
    source = cache / f"{seed.artifact_id}-{seed.version}-sources.jar"
    source.write_bytes(b"must never be read")

    def forbidden_read(_self):
        raise AssertionError("V4 cache census read a candidate body")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read)
    report = scan_m336e_local_cache_names(
        (("maven", cache),), platform="windows", seeds=(seed,)
    )
    assert report["source_body_bytes_read"] == 0
    assert report["excluded_family_ids"] == (seed.family_id,)
    assert report["matches"][0]["matched_metadata_identity"].endswith(
        f"{seed.artifact_id}-{seed.version}-sources.jar"
    )


def test_fresh_metadata_v4_pool_is_optional_metadata_only_and_uses_real_ids():
    seeds = fresh_metadata_candidate_seeds()[:50]

    def fake_probe(seed, *, timestamp, host):
        source_url = (
            "https://repo.maven.apache.org/maven2/"
            + seed.group_id.replace(".", "/")
            + f"/{seed.artifact_id}/{seed.version}/"
            + f"{seed.artifact_id}-{seed.version}-sources.jar"
        )
        receipt_body = {
            "requested_url": source_url,
            "method": "HEAD",
            "final_url": source_url,
            "redirects": (),
            "response_status": 200,
            "relevant_headers": (("content-length", "1000"),),
            "bytes_received": 0,
            "timestamp": timestamp,
            "host": host,
            "request_hash": content_hash(("HEAD", source_url)),
            "response_hash": content_hash((("content-length", "1000"),)),
        }
        row_body = {
            "family_id": seed.family_id,
            "organization_id": seed.organization_id,
            "group_id": seed.group_id,
            "artifact_id": seed.artifact_id,
            "version": seed.version,
            "coordinate": f"{seed.group_id}:{seed.artifact_id}:{seed.version}",
            "requirement": "OPTIONAL",
            "source_url": source_url,
            "pom_url": source_url.rsplit("/", 1)[0]
            + f"/{seed.artifact_id}-{seed.version}.pom",
            "metadata_pom_sha256": content_hash((seed.family_id, "pom")),
            "packaging": "jar",
            "pom_license_declarations": (
                ("Apache-2.0", "Apache License 2.0", content_hash(seed.family_id)),
            ),
            "pom_scm_metadata": (seed.scm_repository,),
            "declared_java_releases": (("java.version", "17"),),
            "source_content_length": 1000,
            "source_sha256_sidecar_available": True,
            "source_sha256_sidecar_value": "1" * 64,
            "source_signature_available": False,
            "scm_repository": seed.scm_repository,
            "scm_ref": seed.scm_ref,
            "scm_commit": "2" * 40,
            "repository_source_prefixes": seed.repository_source_prefixes,
            "metadata_receipt_hashes": (content_hash(receipt_body),),
        }
        return (
            {**row_body, "policy_hash": content_hash(row_body)},
            ({**receipt_body, "receipt_hash": content_hash(receipt_body)},),
        )

    cache = {"source_body_bytes_read": 0, "excluded_family_ids": ()}
    pool, receipts, scenarios = probe_metadata_pool_v4(
        windows_cache=cache,
        karina_cache=cache,
        timestamp="1970-01-01T00:00:00Z",
        host="test",
        probe_one=fake_probe,
        seeds=seeds,
    )
    assert len(validate_metadata_pool_v4(pool)) == 50
    assert pool["candidate_count"] == 50
    assert pool["organization_count"] >= 40
    assert pool["required_candidate_count"] == 0
    assert pool["optional_candidate_count"] == 50
    assert pool["pre_f20_source_body_bytes_received"] == 0
    assert pool["claims_final_eligibility"] is False
    assert receipts["source_jar_get_count"] == 0
    assert receipts["source_body_bytes_received"] == 0
    assert receipts["forbidden_body_request_count"] == 0
    assert scenarios["individual_candidate_scenario_count"] == 50
    assert scenarios["organization_scenario_count"] >= 40
    assert scenarios["claims_final_eligibility"] is False
    assert {
        "without-checksum-sidecars",
        "scm-only-authenticity",
        "multi-license-review",
        "largest-host-concentration",
        "github-metadata-outage",
        "maven-checksum-outage",
        "apache-hosted-correlation-failure",
        "size-tail-failure",
    } <= {item["scenario_id"] for item in scenarios["scenarios"]}

    def forbidden_probe(seed, *, timestamp, host):
        row, _receipts = fake_probe(seed, timestamp=timestamp, host=host)
        source_url = row["source_url"]
        body = {
            "requested_url": source_url,
            "method": "GET",
            "bytes_received": 1,
            "receipt_hash": content_hash((source_url, "GET", 1)),
        }
        return row, (body,)

    with pytest.raises(ValueError, match="size/diversity"):
        # Every candidate is locally rejected by the network safety gate, so the
        # aggregate cannot masquerade as a valid metadata pool.
        probe_metadata_pool_v4(
            windows_cache=cache,
            karina_cache=cache,
            timestamp="1970-01-01T00:00:00Z",
            host="test",
            probe_one=forbidden_probe,
            seeds=seeds,
        )


def test_fresh_scoped_license_does_not_poison_unrelated_source_paths():
    policy = {
        "pom_license_declarations": (("Apache-2.0", "Apache License 2.0", "1" * 64),),
        "metadata_receipt_hashes": ("2" * 64,),
    }
    item = {
        "correspondence": {
            "entries": (
                {
                    "artifact_path": "org/example/A.java",
                    "scm_path": "src/main/java/org/example/A.java",
                    "complete": True,
                },
                {
                    "artifact_path": "org/internal/B.java",
                    "scm_path": "src/main/java/org/internal/B.java",
                    "complete": True,
                },
            )
        },
        "_archive_java_paths": (
            "org/example/A.java",
            "org/internal/B.java",
        ),
        "_legal_inventory_rows": (
            SimpleNamespace(
                container_id="source-jar",
                path="docs/UNCLASSIFIED.txt",
                candidate_role="UNKNOWN_LICENSE_DOCUMENT",
                selected_as_project_license=False,
                spdx_license_id=None,
                spdx_match_status="NO_MATCH",
                receipt_hash="3" * 64,
            ),
            SimpleNamespace(
                container_id="source-jar",
                path="org/internal/UNCLASSIFIED.txt",
                candidate_role="UNKNOWN_LICENSE_DOCUMENT",
                selected_as_project_license=False,
                spdx_license_id=None,
                spdx_match_status="NO_MATCH",
                receipt_hash="4" * 64,
            ),
        ),
        "qualification_errors": (
            "LICENSE:UNKNOWN_LICENSE_DOCUMENT:unclassified=0,unknown_role=2",
        ),
        "source_jar_sha256": "5" * 64,
        "pom_sha256": "6" * 64,
        "scm_archive_sha256": "7" * 64,
        "immutable_scm_commit": "8" * 40,
    }
    _apply_fresh_scoped_qualification(policy, item)
    decisions = item["_scoped_license_by_archive_path"]
    assert decisions["org/example/A.java"]["status"] == "RESOLVED"
    assert (
        decisions["org/internal/B.java"]["status"] == "REVIEW_REQUIRED_AMBIGUOUS_SCOPE"
    )
    assert item["analysis_eligible"] is True
    assert item["candidate_eligible_source_entry_count"] == 1
    assert item["qualification_errors"] == ()
    assert item["qualification_review_findings"] == (
        "LICENSE:UNKNOWN_APPLICABILITY_REVIEW_REQUIRED",
    )


def test_fresh_infeasible_preflight_persists_zero_selector_invocations(
    tmp_path, monkeypatch
):
    from ai_brain.stage3.acquisition import m336e_final_pipeline

    policy = {
        "family_id": "unavailable",
        "organization_id": "example",
        "coordinate": "org.example:unavailable:1.0.0",
        "source_url": (
            "https://repo.maven.apache.org/maven2/org/example/unavailable/1.0.0/"
            "unavailable-1.0.0-sources.jar"
        ),
        "pom_license_declarations": (),
        "metadata_receipt_hashes": (),
    }
    monkeypatch.setattr(
        m336e_final_pipeline,
        "validate_metadata_pool_v4",
        lambda _pool: (policy,),
    )

    def unavailable(_policy, *, vault_root, maven, scm):
        return {
            "family_id": "unavailable",
            "organization_id": "example",
            "coordinate": "org.example:unavailable:1.0.0",
            "source_url": policy["source_url"],
            "source_jar_sha256": "0" * 64,
            "source_jar_size": 0,
            "pom_sha256": "0" * 64,
            "immutable_scm_commit": "0" * 40,
            "scm_archive_sha256": "0" * 64,
            "scm_archive_size": 0,
            "source_tree_hash": "0" * 64,
            "artifact_authenticity_mode": "INCOMPLETE",
            "scoped_license_expressions": (),
            "legal_document_count": 0,
            "unclassified_legal_document_count": 0,
            "unknown_legal_document_role_count": 0,
            "correspondence": None,
            "correspondence_complete_for_all_entries": False,
            "complete_correspondence_paths": (),
            "analysis_eligible": False,
            "candidate_eligible_source_entry_count": 0,
            "qualification_errors": ("SOURCE:UNAVAILABLE",),
            "_raw_source_hashes": (),
            "_canonical_source_hashes": (),
            "_archive_java_paths": (),
            "_legal_inventory_rows": (),
            "_vault_files": (),
            "_performance_seconds": {"unavailable": 0.001},
        }

    authority = tmp_path / "authority.txt"
    authority.write_bytes(
        b"M336E_USER_AUTHORITY_V1\n"
        b"source_use=PRIVATE_LOCAL_ANALYSIS,LOCAL_RESEARCH_EVALUATION,"
        b"DERIVED_KNOWLEDGE_ONLY,RAW_SOURCE_RETENTION,"
        b"PUBLIC_REPRODUCIBLE_EVALUATION\n"
        b"publication_allow=DERIVED_PACK_PUBLICATION,METRICS_ONLY_PUBLICATION\n"
        b"publication_deny=RAW_SOURCE_PUBLICATION,SOURCE_EXCERPT_PUBLICATION\n"
        b"raw_storage=LOCAL_SEALED_VAULT_ONLY\n"
        b"authority_may_narrow=true\n"
        b"authority_may_widen=false\n"
    )
    ledger = RunProtocolLedger(tmp_path / "ledger.jsonl", git_worktrees=(Path.cwd(),))
    result = run_fresh_acquisition_and_preflight(
        pool={"pool_hash": "9" * 64},
        vault_root=tmp_path / "vault",
        authority_statement=authority,
        f20_sha="a" * 40,
        timestamp="1970-01-01T00:00:00Z",
        host="test",
        ledger=ledger,
        selected_source_output=tmp_path / "selected",
        git_worktrees=(Path.cwd(),),
        maven_provider=object(),
        scm_provider=object(),
        acquire_one=unavailable,
    )
    assert result.status == "BLOCKED"
    assert result.selected_manifest is None
    assert result.selector_receipt is None
    assert ledger.receipt().final_event_type == "SELECTABILITY_CENSUS_COMPLETED"
    assert ledger.receipt().selector_invocation_count == 0
    assert ledger.receipt().selector_rerun_count == 0


def test_production_index_census_isolates_exact_parser_failures(tmp_path):
    family = "parser-isolation"
    source_root = tmp_path / "candidates" / family / "sources"
    valid_path = "org/example/Valid.java"
    invalid_path = "org/example/Invalid.java"
    valid = b"package org.example; public class Valid { public void run() {} }\n"
    invalid = b"package org.example; public class {\n"
    for relative, raw in ((valid_path, valid), (invalid_path, invalid)):
        path = source_root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    inspection = SimpleNamespace(
        java_entries=((valid_path, valid), (invalid_path, invalid))
    )
    declarations, evidence_nodes, statuses = _production_index_candidate(
        tmp_path,
        {"family_id": family, "analysis_eligible": True},
        inspection,
        load_production_java_evidence_policy(),
    )
    assert statuses == {valid_path: "PASS", invalid_path: "PARSER_FAILED"}
    assert declarations[valid_path]
    assert invalid_path not in declarations
    assert evidence_nodes


def _new_disclosure_entry(index: int):
    version = f"1.0.{index}"
    return build_disclosed_java_material_entry(
        coordinate=f"org.m336e{index}:candidate{index}:{version}",
        version=version,
        source_url=(
            "https://repo.maven.apache.org/maven2/"
            f"org/m336e{index}/candidate{index}/{version}/candidate{index}-{version}-sources.jar"
        ),
        archive_hash=content_hash((index, "archive")),
        pom_hash=content_hash((index, "pom")),
        raw_source_hashes=(content_hash((index, "raw")),),
        canonical_source_hashes=(content_hash((index, "canonical")),),
        source_tree_hash=content_hash((index, "tree")),
        selected_relative_paths=(),
        declaration_fingerprints=(content_hash((index, "declaration")),),
        scm_revision=f"{index + 1:040x}",
        correspondence_hash=content_hash((index, "correspondence")),
        disclosure_reason="M336E_TEST_APPEND",
        originating_chain="E19-R20-Q20-F20-H20-E20",
    )


@pytest.mark.parametrize("appended_count", (1, 24, 48))
def test_registry_v2_accepts_30_to_future_append_chains(tmp_path, appended_count):
    root = tmp_path / f"registry-{appended_count}"
    shutil.copytree(DEFAULT_REGISTRY_ROOT, root)
    previous = (root / "registry_manifest.json").read_bytes()
    original_entries = {
        path.name: bytes_hash(path.read_bytes())
        for path in (root / "entries").glob("*.json")
    }
    manifest, receipt = append_disclosed_java_entries_v2(
        root,
        tuple(_new_disclosure_entry(index + 1000) for index in range(appended_count)),
        acquisition_run_id=f"m336e.registry-simulation.{appended_count}",
        f20_sha="1" * 40,
    )
    verify_disclosed_java_registry(root)
    assert receipt.previous_entry_count == 30
    assert receipt.resulting_entry_count == 30 + appended_count
    assert len(load_disclosed_java_registry(root)) == 30 + appended_count
    for name, expected in original_entries.items():
        assert bytes_hash((root / "entries" / name).read_bytes()) == expected
    previous_value = json.loads(previous)
    assert manifest.entry_hashes[:30] == tuple(previous_value["entry_hashes"])


def test_registry_v2_rejects_reordering_and_wrong_parent(tmp_path):
    root = tmp_path / "registry"
    shutil.copytree(DEFAULT_REGISTRY_ROOT, root)
    previous_raw = (root / "registry_manifest.json").read_bytes()
    previous = json.loads(previous_raw)
    manifest, receipt = append_disclosed_java_entries_v2(
        root,
        (_new_disclosure_entry(2000),),
        acquisition_run_id="m336e.registry-negative.v1",
        f20_sha="1" * 40,
    )
    prior_manifest_path = root / "manifests" / f"{previous['manifest_hash']}.json"
    from ai_brain.stage3.acquisition.java_disclosed_registry import _load_manifest

    prior_manifest = _load_manifest(prior_manifest_path.read_bytes())
    with pytest.raises(ValueError, match="invalid"):
        verify_disclosure_registry_append_receipt(
            replace(receipt, previous_registry_manifest_hash="9" * 64),
            prior_manifest,
            manifest,
        )
    broken = json.loads((root / "registry_manifest.json").read_text(encoding="utf-8"))
    broken["entry_hashes"][0], broken["entry_hashes"][1] = (
        broken["entry_hashes"][1],
        broken["entry_hashes"][0],
    )
    body = dict(broken)
    body.pop("manifest_hash")
    broken["manifest_hash"] = content_hash(body)
    (root / "registry_manifest.json").write_text(
        canonical_json(broken) + "\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ValueError, match="prefix|snapshot"):
        verify_disclosed_java_registry(root)


def test_registry_v2_rejects_deletion_replacement_semantic_duplicate_and_skipped_parent(
    tmp_path,
):
    original = load_disclosed_java_registry(DEFAULT_REGISTRY_ROOT)[0]

    deletion = tmp_path / "deletion"
    shutil.copytree(DEFAULT_REGISTRY_ROOT, deletion)
    (deletion / "entries" / f"{original.entry_hash}.json").unlink()
    with pytest.raises(ValueError, match="truncated"):
        verify_disclosed_java_registry(deletion)

    replacement = tmp_path / "replacement"
    shutil.copytree(DEFAULT_REGISTRY_ROOT, replacement)
    path = replacement / "entries" / f"{original.entry_hash}.json"
    path.write_bytes(path.read_bytes().replace(b'"version":"', b'"version":"x', 1))
    with pytest.raises(ValueError):
        verify_disclosed_java_registry(replacement)

    semantic = tmp_path / "semantic"
    shutil.copytree(DEFAULT_REGISTRY_ROOT, semantic)
    duplicate = build_disclosed_java_material_entry(
        coordinate=original.coordinate,
        version=original.version,
        source_url=_new_disclosure_entry(3000).source_url,
        archive_hash="1" * 64,
        pom_hash="2" * 64,
        raw_source_hashes=("3" * 64,),
        canonical_source_hashes=("4" * 64,),
        source_tree_hash="5" * 64,
        selected_relative_paths=(),
        declaration_fingerprints=("6" * 64,),
        scm_revision="7" * 40,
        correspondence_hash="8" * 64,
        disclosure_reason="M336E_SEMANTIC_DUPLICATE_TEST",
        originating_chain="E19-R20-Q20-F20-H20-E20",
    )
    with pytest.raises(ValueError, match="duplicate disclosed identity"):
        append_disclosed_java_entries_v2(
            semantic,
            (duplicate,),
            acquisition_run_id="m336e.registry-semantic-negative.v1",
            f20_sha="1" * 40,
        )

    skipped = tmp_path / "skipped"
    shutil.copytree(DEFAULT_REGISTRY_ROOT, skipped)
    append_disclosed_java_entries_v2(
        skipped,
        (_new_disclosure_entry(3100),),
        acquisition_run_id="m336e.registry-first.v1",
        f20_sha="1" * 40,
    )
    head, _receipt = append_disclosed_java_entries_v2(
        skipped,
        (_new_disclosure_entry(3101),),
        acquisition_run_id="m336e.registry-second.v1",
        f20_sha="1" * 40,
    )
    historical = json.loads(
        (DEFAULT_REGISTRY_ROOT / "registry_manifest.json").read_text(encoding="utf-8")
    )
    forged_body = {
        "schema_version": 2,
        "previous_manifest_hash": historical["manifest_hash"],
        "entry_hashes": head.entry_hashes,
    }
    forged = {**forged_body, "manifest_hash": content_hash(forged_body)}
    raw = (canonical_json(forged) + "\n").encode()
    (skipped / "registry_manifest.json").write_bytes(raw)
    (skipped / "manifests" / f"{forged['manifest_hash']}.json").write_bytes(raw)
    with pytest.raises(ValueError, match="skipped|orphan"):
        verify_disclosed_java_registry(skipped)


def test_real_acquisition_producer_and_contract_v2_are_compatible_and_strict():
    legacy = json.loads(
        Path("evaluation/m336d_final_java/h19/acquisition_receipts.json").read_text(
            encoding="utf-8"
        )
    )
    producer = PublicArtifactProducer(
        producer_id="m336e.acquisition-receipts.v2",
        artifact_type="acquisition-receipts",
        relative_path="h20/acquisition_receipts.json",
        schema_version=2,
        success_variants=("SUCCESS",),
        blocked_variants=("BLOCKED",),
        review_required_variants=("REVIEW_REQUIRED",),
        produce=lambda variant: produce_m336e_acquisition_receipts(
            legacy, f20_sha="1" * 40, variant=variant
        ),
    )
    producers = m336e_future_public_producers(legacy)
    assert producers[0].producer_id == producer.producer_id
    report = ProducerContractCompatibilityGate(
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY, producers
    ).run()
    assert report.status == "PASS"
    assert report.public_producer_count == report.covered_producer_count == 12
    assert (
        report.declared_producer_variant_count
        == report.tested_producer_variant_count
        == 36
    )
    assert report.uncontracted_produced_artifact_count == 0
    assert report.contract_type_without_producer_or_legacy_count == 0
    assert report.ambiguous_path_contract_count == 0

    forged = produce_m336e_acquisition_receipts(
        legacy, f20_sha="1" * 40, variant="SUCCESS"
    )
    forged["receipts"][0]["unexpected"] = True
    body = dict(forged)
    body.pop("report_hash")
    forged["report_hash"] = content_hash(body)
    with pytest.raises(ValueError, match="unknown nested field"):
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h20/acquisition_receipts.json", canonical_public_json(forged)
        )

    duplicate_key = canonical_public_json(
        produce_m336e_acquisition_receipts(legacy, f20_sha="1" * 40, variant="SUCCESS")
    ).replace(
        b'{"acquisition_run_id":', b'{"schema_version":2,"acquisition_run_id":', 1
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h20/acquisition_receipts.json", duplicate_key
        )


def test_qualification_contract_preserves_all_typed_candidate_decisions():
    qualification = {
        "schema_version": 1,
        "candidate_count": 1,
        "candidates": (
            {
                "family_id": "disclosed-family",
                "source_jar_sha256": "1" * 64,
                "java_file_count": 3,
                "legal_document_count": 2,
                "unknown_legal_document_role_count": 0,
                "correspondence_complete_file_count": 3,
                "analysis_eligible": True,
            },
        ),
        "report_hash": "2" * 64,
    }
    value = produce_m336e_qualification_summary(
        "SUCCESS",
        qualification=qualification,
        census={"analysis_eligible_file_count": 3},
        overlap={"selected_root_overlap_count": 0},
    )
    validation = M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
        "h20/qualification_summary.json", canonical_public_json(value)
    )
    assert validation.status == "PASS"
    assert value["candidate_count"] == len(value["candidate_decisions"]) == 1
    assert value["candidate_decisions"][0]["scoped_license_decision"] == "RESOLVED"
    assert value["freshness_overlap_count"] == 0

    forged = json.loads(canonical_json(value))
    forged["candidate_decisions"][0]["unexpected"] = True
    body = dict(forged)
    body.pop("report_hash")
    forged["report_hash"] = content_hash(body)
    with pytest.raises(ValueError, match="unknown nested field"):
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h20/qualification_summary.json", canonical_public_json(forged)
        )
