from __future__ import annotations

import io
import runpy
import struct
import warnings
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition import maven_provenance as maven
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    disclosed_candidate_match,
    load_disclosed_java_corpus_denylist,
    load_m336a_disclosed_candidate_denylist,
)
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    verify_m336_git_freeze_protocol,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    FinalArtifactRole,
    build_final_artifact_role_manifest,
    dump_final_artifact_role_manifest,
    extract_disclosure_claims,
    load_final_artifact_role_manifest,
    verify_disclosure_claim_set,
    verify_final_artifact_role_manifest,
    verify_role_aware_disclosure,
)
from ai_brain.stage3.acquisition.m336a_readiness import (
    M336AReadinessDecision,
    evaluate_m336a_readiness,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    inspect_source_archive,
    license_text_evidence,
    maven_coordinate,
    parse_maven_pom,
    validate_repository_exchange,
    verify_sha256_sidecar,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    resolve_historical_license_evidence as resolve_license_evidence,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION,
    ArtifactDigestEvidence,
    ArtifactQualificationDecision,
    CandidateQualificationStatus,
    CandidateRequirement,
    LicenseClaim,
    LicenseEvidenceMode,
    ProvenanceStatus,
    RepositoryMetadataEvidence,
    SourceTreeCorrespondence,
    build_provenance_audit_event,
    build_provenance_envelope,
    execute_candidate_qualification,
    qualify_artifact,
    qualify_candidate_set,
)

ROOT = Path(__file__).resolve().parents[1]
F15 = "d377a206bb251508b94680dd267f0c5cd02dd2aa"
H15 = "ae86c630a4141dc97cfe97fd4a46d2eeaacc5831"
E15 = "b4f8b881ab15e995c8df9e17e4704f5dec34e028"


def _coordinate():
    return maven_coordinate(group_id="org.example", artifact_id="demo", version="1.2.3")


def _claim(spdx="Apache-2.0"):
    body = {
        "spdx_identifier": spdx,
        "declaration_source": "MAVEN_POM",
        "declared_name": spdx,
    }
    return LicenseClaim(**body, declaration_hash=content_hash(body))


def _license(exact=True):
    digest = maven.apache_2_license_identity() if exact else "e" * 64
    return maven.LicenseTextEvidence(
        "LICENSE", digest, digest, maven.apache_2_license_identity(), exact
    )


def _correspondence(*, unmatched=0, ambiguous=0):
    body = {
        "entries": (),
        "exact_match_count": 1 if not unmatched and not ambiguous else 0,
        "relocated_match_count": 0,
        "generated_match_count": 0,
        "unmatched_count": unmatched,
        "ambiguous_count": ambiguous,
        "eligible_entry_count": 1 if not unmatched and not ambiguous else 0,
    }
    return SourceTreeCorrespondence(**body, correspondence_hash=content_hash(body))


def _zip(entries, *, attributes=None):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as opened:
            for name, raw in entries:
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                if attributes and name in attributes:
                    info.create_system = 3
                    info.external_attr = attributes[name]
                opened.writestr(info, raw)
    return stream.getvalue()


def _pom(
    *,
    group="org.example",
    artifact="demo",
    version="1.2.3",
    license_name="Apache License, Version 2.0",
):
    return f"""<project>
      <modelVersion>4.0.0</modelVersion><groupId>{group}</groupId>
      <artifactId>{artifact}</artifactId><version>{version}</version>
      <licenses><license><name>{license_name}</name><url>https://www.apache.org/licenses/LICENSE-2.0.txt</url></license></licenses>
      <scm><connection>scm:git:https://github.com/example/demo.git</connection><url>https://github.com/example/demo</url></scm>
    </project>""".encode()


def _decision(
    index,
    *,
    status=CandidateQualificationStatus.ELIGIBLE,
    requirement=CandidateRequirement.OPTIONAL,
):
    coordinate = maven_coordinate(
        group_id="org.example", artifact_id=f"demo{index}", version="1"
    )
    body = {
        "coordinate": coordinate,
        "requirement": requirement,
        "status": status,
        "evidence_mode": LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE,
        "reasons": (status.value,),
        "eligible_root": f"root-{index}"
        if status is CandidateQualificationStatus.ELIGIBLE
        else None,
        "provenance_identity_hash": f"{index:064x}",
    }
    return ArtifactQualificationDecision(**body, decision_hash=content_hash(body))


def _envelope(*, sidecar_verified=True):
    coordinate = _coordinate()
    artifact = ArtifactDigestEvidence("a" * 64, "b" * 64, sidecar_verified, None, 10)
    repository = RepositoryMetadataEvidence(
        "repo.maven.apache.org",
        f"{coordinate.repository}/{coordinate.canonical_repository_path}",
        f"{coordinate.repository}/{coordinate.canonical_repository_path}",
        (),
        10,
        "application/java-archive",
        "c" * 64,
    )
    audit = build_provenance_audit_event(
        acquired_at="2026-09-04T00:00:00Z",
        host="fixture",
        acquisition_run_id="fixture",
        network_receipt_hashes=("c" * 64,),
    )
    return build_provenance_envelope(
        schema_version=SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION,
        coordinate=coordinate,
        artifact_digest=artifact,
        repository_metadata=repository,
        pom_digest=artifact,
        license_claims=(_claim(),),
        license_texts=(_license(),),
        license_evidence_mode=LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE,
        license_status=ProvenanceStatus.VERIFIED,
        scm_revision=None,
        correspondence=None,
        conflicts=(),
        audit_event=audit,
    )


@pytest.mark.parametrize(
    "case", range(18), ids=lambda value: f"license-case-{value + 1:02d}"
)
def test_provenance_license_and_qualification_matrix(case, monkeypatch):
    if case == 0:
        mode, status, _ = resolve_license_evidence(
            pom_claims=(),
            embedded_texts=(_license(),),
            scm_text=None,
            immutable_scm_verified=False,
            correspondence=None,
        )
        assert (mode, status) == (
            LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE,
            ProvenanceStatus.VERIFIED,
        )
    elif case == 1:
        mode, status, _ = resolve_license_evidence(
            pom_claims=(_claim(),),
            embedded_texts=(),
            scm_text=_license(),
            immutable_scm_verified=True,
            correspondence=_correspondence(),
        )
        assert (mode, status) == (
            LicenseEvidenceMode.POM_PLUS_IMMUTABLE_SCM_LICENSE,
            ProvenanceStatus.VERIFIED,
        )
    elif case == 2:
        assert (
            resolve_license_evidence(
                pom_claims=(_claim(),),
                embedded_texts=(),
                scm_text=None,
                immutable_scm_verified=False,
                correspondence=None,
            )[1]
            is ProvenanceStatus.REVIEW_REQUIRED
        )
    elif case == 3:
        assert (
            resolve_license_evidence(
                pom_claims=(_claim(),),
                embedded_texts=(_license(False),),
                scm_text=None,
                immutable_scm_verified=False,
                correspondence=None,
            )[1]
            is ProvenanceStatus.CONFLICT
        )
    elif case == 4:
        assert (
            resolve_license_evidence(
                pom_claims=(_claim(),),
                embedded_texts=(),
                scm_text=_license(False),
                immutable_scm_verified=True,
                correspondence=_correspondence(),
            )[1]
            is ProvenanceStatus.CONFLICT
        )
    elif case == 5:
        with pytest.raises(ValueError, match="GAV"):
            parse_maven_pom(_pom(group="invalid"), _coordinate())
    elif case in {6, 7}:
        with pytest.raises(ValueError, match="mismatch"):
            verify_sha256_sidecar(b"artifact", b"0" * 64)
    elif case == 8:
        assert (
            resolve_license_evidence(
                pom_claims=(_claim(),),
                embedded_texts=(),
                scm_text=_license(),
                immutable_scm_verified=False,
                correspondence=_correspondence(),
            )[1]
            is ProvenanceStatus.REVIEW_REQUIRED
        )
    elif case == 9:
        assert (
            resolve_license_evidence(
                pom_claims=(_claim(),),
                embedded_texts=(),
                scm_text=_license(),
                immutable_scm_verified=True,
                correspondence=_correspondence(unmatched=1),
            )[1]
            is ProvenanceStatus.REVIEW_REQUIRED
        )
    elif case == 10:
        with pytest.raises(ValueError, match="DTD"):
            parse_maven_pom(
                b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///x">]><project/>',
                _coordinate(),
            )
    elif case == 11:
        coordinate = _coordinate()
        url = f"{coordinate.repository}/{coordinate.canonical_repository_path}"
        with pytest.raises(ValueError, match="allowlist"):
            validate_repository_exchange(
                coordinate,
                requested_url=url,
                final_url="https://evil.example/x",
                redirect_chain=("https://evil.example/x",),
            )
    elif case == 12:
        monkeypatch.setattr(
            maven, "APACHE_2_LICENSE_RAW_SHA256", bytes_hash(b"canonical\n")
        )
        evidence = license_text_evidence("LICENSE", b"prefix Apache License suffix\n")
        assert not evidence.exact_match
    elif case == 13:
        with pytest.raises(ValueError, match="conflicting"):
            inspect_source_archive(
                _zip((("LICENSE", b"one"), ("META-INF/LICENSE", b"two")))
            )
    elif case == 14:
        calls = []
        decisions = (
            _decision(0),
            _decision(1),
            _decision(2, status=CandidateQualificationStatus.INELIGIBLE_LICENSE),
        )
        result, _ = execute_candidate_qualification(
            decisions,
            qualifier=lambda item: item,
            selector=lambda roots: calls.append(roots) or roots,
            minimum_eligible_roots=2,
        )
        assert result["status"] == "READY_FOR_SINGLE_SELECTION" and len(calls) == 1
    elif case == 15:
        result = qualify_candidate_set(
            (
                _decision(0),
                _decision(
                    1,
                    status=CandidateQualificationStatus.INELIGIBLE_LICENSE,
                    requirement=CandidateRequirement.REQUIRED,
                ),
            ),
            minimum_eligible_roots=1,
        )
        assert result["status"] == "BLOCKED"
    elif case == 16:
        assert (
            qualify_candidate_set((_decision(0),), minimum_eligible_roots=2)["status"]
            == "BLOCKED"
        )
    else:
        assert (
            qualify_artifact(
                _envelope(sidecar_verified=False),
                requirement=CandidateRequirement.OPTIONAL,
                eligible_root="root",
            ).status
            is CandidateQualificationStatus.INELIGIBLE_PROVENANCE
        )


@pytest.mark.parametrize(
    "case", range(22), ids=lambda value: f"security-mutation-{value + 1:02d}"
)
def test_network_archive_and_metadata_mutations_fail_closed(case, monkeypatch):
    coordinate = _coordinate()
    url = f"{coordinate.repository}/{coordinate.canonical_repository_path}"
    with pytest.raises((ValueError, TypeError, zipfile.BadZipFile)):
        if case == 0:
            maven_coordinate(
                group_id="x",
                artifact_id="a",
                version="1",
                repository="https://evil.example/maven2",
            )
        elif case == 1:
            validate_repository_exchange(
                coordinate, requested_url=url, final_url="https://evil.example/x"
            )
        elif case == 2:
            validate_repository_exchange(
                coordinate, requested_url=url, final_url=url.replace("https:", "http:")
            )
        elif case == 3:
            verify_sha256_sidecar(b"x", None)
        elif case == 4:
            verify_sha256_sidecar(b"x", b"f" * 64)
        elif case == 5:
            raw = _zip((("A.java", b"class A{}"), ("A.java", b"class B{}")))
            inspect_source_archive(raw)
        elif case == 6:
            inspect_source_archive(_zip((("../A.java", b"x"),)))
        elif case == 7:
            inspect_source_archive(_zip((("/A.java", b"x"),)))
        elif case == 8:
            inspect_source_archive(
                _zip((("link", b"target"),), attributes={"link": (0o120777 << 16)})
            )
        elif case == 9:
            raw = bytearray(_zip((("A.java", b"class A{}"),)))
            local = raw.find(b"PK\x03\x04")
            central = raw.find(b"PK\x01\x02")
            struct.pack_into(
                "<H", raw, local + 6, struct.unpack_from("<H", raw, local + 6)[0] | 1
            )
            struct.pack_into(
                "<H",
                raw,
                central + 8,
                struct.unpack_from("<H", raw, central + 8)[0] | 1,
            )
            inspect_source_archive(bytes(raw))
        elif case == 10:
            monkeypatch.setattr(maven, "MAX_ARCHIVE_ENTRIES", 0)
            inspect_source_archive(_zip((("A.java", b"x"),)))
        elif case == 11:
            monkeypatch.setattr(maven, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 0)
            inspect_source_archive(_zip((("A.java", b"x"),)))
        elif case == 12:
            monkeypatch.setattr(maven, "MAX_ARCHIVE_ENTRY_BYTES", 0)
            inspect_source_archive(_zip((("A.java", b"x"),)))
        elif case == 13:
            monkeypatch.setattr(maven, "MAX_COMPRESSION_RATIO", 1)
            inspect_source_archive(_zip((("A.java", b"0" * 10_000),)))
        elif case == 14:
            inspect_source_archive(_zip((("é.java", b"x"), ("e\u0301.java", b"y"))))
        elif case == 15:
            inspect_source_archive(
                _zip((("LICENSE", b"one"), ("META-INF/LICENSE", b"two")))
            )
        elif case == 16:
            inspect_source_archive(_zip((("LICENSE", b"\xff\xfe"),)))
        elif case == 17:
            parse_maven_pom(b"<project>", coordinate)
        elif case == 18:
            parse_maven_pom(b"<!DOCTYPE project><project/>", coordinate)
        elif case == 19:
            parse_maven_pom(
                b'<!DOCTYPE x [<!ENTITY e SYSTEM "https://evil.example">]><project/>',
                coordinate,
            )
        elif case == 20:
            maven_coordinate(
                group_id="x", artifact_id="a", version="1", classifier="binary"
            )
        else:
            parse_maven_pom(_pom(version="9.9.9"), coordinate)


def _disclosure_fixture(index):
    digest = f"{index + 1:064x}"
    fixtures = (
        (
            "evaluation/m336_final_java/source_acquisition_receipts.json",
            {"archives": [{"source_archive_sha256": digest}]},
        ),
        (
            "evaluation/m336_final_java/source_acquisition_receipts.json",
            {"archives": [{"raw_source_hashes": [digest]}]},
        ),
        (
            "evaluation/m336_final_java/selector_receipt.json",
            {"selected_relative_paths": ["root/Secret.java"]},
        ),
        (
            "evaluation/m336_final_java/source_acquisition_receipts.json",
            {"archives": [{"source_tree_hash": digest}]},
        ),
        (
            "evaluation/m336_final_java/production_summary.json",
            {"target_identities": ["java:secret.Target#m()V"]},
        ),
        (
            "evaluation/m336_final_java/production_summary.json",
            {"production_output_hash": digest},
        ),
        (
            "evaluation/m336_final_java/production_summary.json",
            {"candidate_pack_hash": digest},
        ),
        ("evaluation/m336_final_java/oracle/output.json", {"oracle_hash": digest}),
        ("evaluation/m336_final_java/goldens/golden.json", {"golden_hash": digest}),
        ("evaluation/m336_final_java/final_decision.json", {"decision_hash": digest}),
    )
    path, body = fixtures[index]
    value = next(
        item
        for item in (digest, "root/Secret.java", "java:secret.Target#m()V")
        if item in canonical_json(body)
    )
    return {path: (canonical_json(body) + "\n").encode()}, value


@pytest.mark.parametrize(
    "case", range(20), ids=lambda value: f"disclosure-mutation-{value + 1:02d}"
)
def test_disclosure_mutation_battery_blocks(case):
    if case < 10:
        h, secret = _disclosure_fixture(case)
        manifest = build_final_artifact_role_manifest(h)
        report = verify_role_aware_disclosure(
            {"src/leak.py": secret.encode()}, h, manifest
        )
        assert not report.passed and secret in report.leaked_tokens
        return
    h, _ = _disclosure_fixture(5)
    manifest = build_final_artifact_role_manifest(h)
    claims = extract_disclosure_claims(h, manifest)
    if case == 10:
        binding = manifest.bindings[0]
        changed = replace(
            manifest, bindings=(replace(binding, role=FinalArtifactRole.PROCESS_AUDIT),)
        )
        body = asdict(changed)
        body.pop("manifest_hash")
        with pytest.raises(ValueError, match="weakened"):
            verify_final_artifact_role_manifest(
                replace(changed, manifest_hash=content_hash(body)), h
            )
    elif case == 11:
        raw = dump_final_artifact_role_manifest(manifest).replace(
            b'"FINAL_PRODUCTION_OUTPUT"', b'"UNKNOWN_ROLE"'
        )
        with pytest.raises(ValueError, match="unknown"):
            load_final_artifact_role_manifest(raw)
    elif case == 12:
        with pytest.raises(ValueError, match="weakened"):
            verify_final_artifact_role_manifest(replace(manifest, bindings=()), h)
    elif case == 13:
        binding = manifest.bindings[0]
        with pytest.raises(ValueError, match="weakened"):
            verify_final_artifact_role_manifest(
                replace(manifest, bindings=(binding, binding)), h
            )
    elif case == 14:
        neutral = {
            "evaluation/m336_final_java/renamed_audit.json": next(iter(h.values()))
        }
        with pytest.raises(ValueError, match="neutral role"):
            extract_disclosure_claims(
                neutral, build_final_artifact_role_manifest(neutral)
            )
    elif case == 15:
        moved = replace(claims[0], field_path="$.moved")
        with pytest.raises(ValueError, match="claim"):
            verify_disclosure_claim_set(h, manifest, (moved,))
    elif case in {16, 17}:
        with pytest.raises(ValueError, match="incomplete"):
            verify_disclosure_claim_set(h, manifest, ())
    elif case == 18:
        changed = replace(claims[0], predeclared=True)
        body = asdict(changed)
        body.pop("claim_hash")
        changed = replace(changed, claim_hash=content_hash(body))
        with pytest.raises(ValueError, match="predeclared"):
            verify_disclosure_claim_set(h, manifest, (changed,))
    else:
        source = b"class Secret {}\n"
        h = {
            "evaluation/m336_final_java/source_snapshots/root/Secret.java": source,
            "evaluation/m336_final_java/source_copy_audit.txt": source,
        }
        report = verify_role_aware_disclosure(
            {"docs/pre_freeze.txt": source}, h, build_final_artifact_role_manifest(h)
        )
        assert not report.passed and report.leaked_paths


@pytest.mark.parametrize(
    "allowed",
    (
        "META-INF/LICENSE",
        "META-INF/LICENSE.txt",
        maven.APACHE_2_LICENSE_RAW_SHA256,
        "docs/m336_final_semantic_metrics.md",
        "docs/m336_final_source_inventory.md",
        "evaluation/m336_final_java/role_manifest.json",
        "evaluation/m336_final_java/selector_receipt.json",
        "0" * 64,
    ),
)
def test_predeclared_or_role_neutral_values_are_allowed(allowed):
    h = {"evaluation/m336_final_java/production_process_audit.json": b'{"count":0}\n'}
    report = verify_role_aware_disclosure(
        {"docs/predeclared.md": allowed.encode()},
        h,
        build_final_artifact_role_manifest(h),
    )
    assert report.passed and not report.leaked_tokens


def test_accumulated_denylist_blocks_all_disclosed_identity_classes():
    current = load_m336a_disclosed_candidate_denylist()
    accumulated = load_disclosed_java_corpus_denylist()
    assert len(current["coordinates"]) == len(current["archive_hashes"]) == 3
    assert (
        len(current["raw_source_hashes"])
        == len(current["canonical_text_hashes"])
        == 1024
    )
    for coordinate, archive, url in zip(
        current["coordinates"],
        current["archive_hashes"],
        current["source_archive_urls"],
        strict=True,
    ):
        assert disclosed_candidate_match(coordinate=coordinate)
        assert disclosed_candidate_match(archive_hash=archive)
        assert disclosed_candidate_match(source_url=url)
        assert disclosed_candidate_match(
            archive_hash=archive, source_url="https://repo.maven.apache.org/renamed.jar"
        )
    assert disclosed_candidate_match(
        canonical_source_hashes=(current["canonical_text_hashes"][0],)
    ) == ("CANONICAL_SOURCE_BYTES",)
    assert disclosed_candidate_match(
        declaration_fingerprints=(current["declaration_fingerprints"][0],)
    ) == ("DECLARATION_FINGERPRINT",)
    assert accumulated["manifest_hash"]


def test_historical_acquisition_receipt_uses_exact_license_not_substring(
    tmp_path, monkeypatch
):
    namespace = runpy.run_path(str(ROOT / "scripts/m336_acquire_select_final_java.py"))
    canonical = b"fixture canonical license\n"
    monkeypatch.setattr(maven, "APACHE_2_LICENSE_RAW_SHA256", bytes_hash(canonical))
    family = SimpleNamespace(
        family_id="fixture",
        version="1",
        source_archive_url="https://repo.maven.apache.org/fixture-sources.jar",
        license_spdx="Apache-2.0",
    )
    archive = tmp_path / "exact.jar"
    archive.write_bytes(
        _zip((("META-INF/LICENSE", canonical), ("p/A.java", b"class A {}\n")))
    )
    exact = namespace["_license_receipt"](archive, family, "2026-09-04T00:00:00Z")
    assert exact["qualification_status"] == "ELIGIBLE"
    fake = tmp_path / "fake.jar"
    fake.write_bytes(
        _zip((("META-INF/LICENSE", b"this says Apache License but is not it"),))
    )
    review = namespace["_license_receipt"](fake, family, "2026-09-04T00:00:00Z")
    assert review["qualification_status"] == "REVIEW_REQUIRED"


def test_historical_role_manifest_roundtrip_and_f15_h15_e15_protocol():
    raw = (ROOT / "evaluation/m336_final_java/role_manifest.json").read_bytes()
    manifest = load_final_artifact_role_manifest(raw)
    assert dump_final_artifact_role_manifest(manifest) == raw
    report = verify_m336_git_freeze_protocol(
        ROOT,
        f15_sha=F15,
        h15_sha=H15,
        e15_sha=E15,
        upstream="origin/exp/stage3-m336-fresh-java-freeze",
    )
    assert report.passed and report.protocol_integrity == "PASS"
    assert report.committed_role_manifest_matches
    assert report.historical_false_disclosure_token_count == 0
    assert report.historical_experiment_outcome == "OUTCOME_C_BLOCKED"


@pytest.mark.parametrize(
    "case", range(9), ids=lambda value: f"role-serialization-mutation-{value + 1:02d}"
)
def test_role_manifest_serialization_mutations_fail_closed(case):
    h = {
        "evaluation/m336_final_java/final_decision.json": b'{"decision_hash":"'
        + b"a" * 64
        + b'"}\n',
        "evaluation/m336_final_java/production_summary.json": b'{"production_output_hash":"'
        + b"b" * 64
        + b'"}\n',
    }
    manifest = build_final_artifact_role_manifest(h)
    raw = dump_final_artifact_role_manifest(manifest)
    if case == 0:
        mutated = raw.replace(b'{"bindings":', b'{"bindings":[],"bindings":', 1)
    elif case == 1:
        mutated = raw.replace(b'"schema_version":2', b'"schema_version":1')
    elif case == 2:
        mutated = raw.replace(b'"relative_path":', b'"extra":0,"relative_path":', 1)
    elif case == 3:
        mutated = raw.replace(b'"bindings":[', b'"bindings":{', 1).replace(
            b'],"manifest_hash"', b'},"manifest_hash"', 1
        )
    elif case == 4:
        mutated = raw.replace(b'"FINAL_DECISION"', b'"UNKNOWN"', 1)
    elif case == 5:
        changed = replace(manifest, bindings=tuple(reversed(manifest.bindings)))
        mutated = (canonical_json(asdict(changed)) + "\n").encode()
    elif case == 6:
        changed = replace(
            manifest, bindings=(manifest.bindings[0], manifest.bindings[0])
        )
        mutated = (canonical_json(asdict(changed)) + "\n").encode()
    elif case == 7:
        mutated = raw.replace(manifest.manifest_hash.encode(), b"0" * 64)
    else:
        mutated = raw.replace(b'{"bindings":', b'{ "bindings":', 1)
    with pytest.raises((ValueError, TypeError)):
        load_final_artifact_role_manifest(mutated)


def test_readiness_gate_is_closed_and_mutation_complete():
    values = {
        name: True
        for name in (
            "artifact_coordinate_verification",
            "archive_pom_checksum_verification",
            "immutable_scm_revision_verification",
            "exact_license_text_verification",
            "eligible_source_correspondence",
            "every_candidate_has_typed_receipt",
            "optional_rejection_does_not_abort",
            "typed_role_manifest_roundtrip",
            "historical_role_manifest_matches",
            "exact_historical_chain",
            "corrected_protocol_integrity",
            "historical_outcome_remains_c",
            "ruff",
            "targeted_tests",
            "windows_full_suite",
            "karina_full_suite",
            "windows_slow_test_three_of_three",
            "worktrees_clean",
            "branch_upstream_equal",
        )
    }
    values.update(
        {
            name: 0
            for name in (
                "conflicting_evidence_accepted",
                "pom_only_auto_verified",
                "selector_rerun_count",
                "metrics_used_for_qualification",
                "future_selector_acceptance_of_disclosed_artifact",
                "malformed_role_manifests_accepted",
                "historical_false_disclosure_token_count",
                "unblocked_genuine_disclosure_mutations",
                "caller_removable_derived_secrets",
                "unknown_artifact_roles_accepted",
                "frozen_code_mutation_count",
                "platform_independent_difference_count",
            )
        }
    )
    values.update(
        selector_invocation_count_after_qualification=1,
        denied_coordinate_count=3,
        denied_archive_hash_count=3,
        new_untouched_corpus_acquired=False,
    )
    assert (
        evaluate_m336a_readiness(values).decision
        is M336AReadinessDecision.READY_FOR_FRESH_JAVA_FREEZE_V2
    )
    for key, value in values.items():
        changed = {
            **values,
            key: (not value if isinstance(value, bool) else value + 1),
        }
        assert (
            evaluate_m336a_readiness(changed).decision is M336AReadinessDecision.BLOCKED
        )
