"""Frozen M-33.6b Maven provenance policy and one production coordinator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    DisclosedMaterialMatchReport,
    match_disclosed_material,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    ArchiveInspection,
    MavenCentralProvenanceProvider,
    canonical_source_bytes,
    correspond_source_trees,
    inspect_source_archive,
    license_text_evidence,
    maven_coordinate,
    parse_maven_pom,
    resolve_license_evidence,
)
from ai_brain.stage3.acquisition.scm_revision import (
    ScmRevisionProvider,
    canonical_github_repository,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION,
    ArtifactQualificationDecision,
    CandidateRequirement,
    SourceArtifactCoordinate,
    SourceArtifactProvenanceEnvelope,
    build_provenance_audit_event,
    build_provenance_envelope,
    dump_source_artifact_provenance_envelope,
    qualify_artifact,
    qualify_candidate_set,
    verify_artifact_qualification_decision,
    verify_candidate_qualification_set,
    verify_source_artifact_provenance_envelope,
)

M336B_CANDIDATE_POLICY_VERSION = "m336b.maven-candidate-policy.v1"
M336B_TARGET_RELEASE = 21


class AcquisitionPolicyMode(StrEnum):
    FINAL = "FINAL"
    DEVELOPMENT_DISCLOSED_REHEARSAL = "DEVELOPMENT_DISCLOSED_REHEARSAL"


@dataclass(frozen=True)
class FrozenMavenSourceCandidate:
    family_id: str
    coordinate: SourceArtifactCoordinate
    requirement: CandidateRequirement
    expected_scm_repository: str
    requested_scm_ref: str
    repository_source_prefixes: tuple[str, ...]
    java_release: int
    metadata_pom_sha256: str
    source_content_length: int
    source_sha256_sidecar_available: bool
    source_signature_available: bool
    declared_scm_identities: tuple[str, ...]
    policy_hash: str


@dataclass(frozen=True)
class AcquiredMavenSourceCandidate:
    policy: FrozenMavenSourceCandidate
    envelope: SourceArtifactProvenanceEnvelope
    qualification: ArtifactQualificationDecision
    disclosed_match: DisclosedMaterialMatchReport
    root: Path
    archive_inspection: ArchiveInspection
    source_archive: bytes
    pom: bytes
    scm_archive: bytes
    raw_source_hashes: tuple[str, ...]
    canonical_source_hashes: tuple[str, ...]


@dataclass(frozen=True)
class MavenCandidateAcquisitionResult:
    policy_version: str
    policy_mode: AcquisitionPolicyMode
    candidates: tuple[AcquiredMavenSourceCandidate, ...]
    qualification_set: dict
    selector_invocation_count: int
    selector_rerun_count: int
    development_denylist_override_count: int
    report_hash: str


def frozen_m336b_candidate_pool() -> tuple[FrozenMavenSourceCandidate, ...]:
    """Metadata-only pool frozen before F17; no body-derived hash is included."""

    specifications = (
        (
            "jackson-databind",
            "com.fasterxml.jackson.core",
            "jackson-databind",
            "2.20.0",
            "https://github.com/FasterXML/jackson-databind.git",
            "refs/tags/jackson-databind-2.20.0",
            ("src/main/java/",),
            "cefefed01dd2c0d96a88e101bb3e065fc150063b498e301a938c690b02bcf3ce",
            1_246_942,
            True,
            True,
            ("scm:git:git@github.com:FasterXML/jackson-databind.git",),
        ),
        (
            "log4j-api",
            "org.apache.logging.log4j",
            "log4j-api",
            "2.25.2",
            "https://github.com/apache/logging-log4j2.git",
            "refs/tags/rel/2.25.2",
            ("log4j-api/src/main/java/",),
            "0956096a2502408c958a83174f2b6a57dcb2e5b07bb914c848732b44b8abbdc3",
            293_959,
            False,
            True,
            (),
        ),
        (
            "reactor-core",
            "io.projectreactor",
            "reactor-core",
            "3.7.9",
            "https://github.com/reactor/reactor-core.git",
            "refs/tags/v3.7.9",
            ("reactor-core/src/main/java/",),
            "3fce4a2502cd5a47fd3622ccdbd711b217a36d99b41c4c312923fedf8b31cd3b",
            2_090_678,
            True,
            True,
            ("scm:git:git://github.com/reactor/reactor-core",),
        ),
        (
            "picocli",
            "info.picocli",
            "picocli",
            "4.7.7",
            "https://github.com/remkop/picocli.git",
            "refs/tags/v4.7.7",
            ("src/main/java/",),
            "1b18d363134df66631d2b9f7475068d734225ba389cdf9082a1bd8bda90d57d3",
            492_153,
            True,
            True,
            ("scm:git:https://github.com/remkop/picocli.git",),
        ),
        (
            "httpcore5",
            "org.apache.httpcomponents.core5",
            "httpcore5",
            "5.3.6",
            "https://github.com/apache/httpcomponents-core.git",
            "refs/tags/rel/v5.3.6",
            ("httpcore5/src/main/java/",),
            "8e37043c6fc40289fe3f0cafd33d0d7e1a10ace4f74495bbc5be39586614718f",
            830_717,
            False,
            True,
            (),
        ),
        (
            "gson",
            "com.google.code.gson",
            "gson",
            "2.13.2",
            "https://github.com/google/gson.git",
            "refs/tags/gson-parent-2.13.2",
            ("gson/src/main/java/",),
            "3aa06aa7c0f9af092961a42d09578e4324be146348a0ee6ed47857f7c2677b76",
            207_421,
            True,
            True,
            (),
        ),
    )
    result = []
    for (
        family,
        group,
        artifact,
        version,
        scm_repository,
        scm_ref,
        prefixes,
        pom_hash,
        length,
        sidecar,
        signature,
        declared_scm_identities,
    ) in specifications:
        body = {
            "family_id": family,
            "coordinate": maven_coordinate(
                group_id=group, artifact_id=artifact, version=version
            ),
            "requirement": CandidateRequirement.OPTIONAL,
            "expected_scm_repository": scm_repository,
            "requested_scm_ref": scm_ref,
            "repository_source_prefixes": prefixes,
            "java_release": M336B_TARGET_RELEASE,
            "metadata_pom_sha256": pom_hash,
            "source_content_length": length,
            "source_sha256_sidecar_available": sidecar,
            "source_signature_available": signature,
            "declared_scm_identities": declared_scm_identities,
        }
        result.append(
            FrozenMavenSourceCandidate(**body, policy_hash=content_hash(body))
        )
    return tuple(result)


def disclosed_m336a_rehearsal_pool() -> tuple[FrozenMavenSourceCandidate, ...]:
    specifications = (
        (
            "google-guava",
            "com.google.guava",
            "guava",
            "33.4.8-jre",
            "https://github.com/google/guava.git",
            "refs/tags/v33.4.8",
            ("guava/src/",),
            "04365d4b6ef22c8cf9349fe628069fc3e81a2c838351402ef4e95f9e757beebc",
            1_847_395,
            False,
            (),
        ),
        (
            "apache-commons-collections4",
            "org.apache.commons",
            "commons-collections4",
            "4.5.0",
            "https://github.com/apache/commons-collections.git",
            "refs/tags/rel/commons-collections-4.5.0",
            ("src/main/java/",),
            "c700f998e1d7a6a5c0aef1d4ceeb6bac7d1702dd6d6eda73a17d67f5d6f2467d",
            804_556,
            False,
            ("scm:git:http://gitbox.apache.org/repos/asf/commons-collections.git",),
        ),
        (
            "caffeine",
            "com.github.ben-manes.caffeine",
            "caffeine",
            "3.2.0",
            "https://github.com/ben-manes/caffeine.git",
            "refs/tags/v3.2.0",
            ("caffeine/src/main/java/",),
            "bf418ab677a31782502229a8fb35bf573f88a36678ec076d6e9337d383e5eae6",
            164_384,
            True,
            ("scm:git:https://github.com/ben-manes/caffeine.git",),
        ),
    )
    result = []
    for (
        family,
        group,
        artifact,
        version,
        repository,
        ref,
        prefixes,
        pom_hash,
        length,
        sidecar,
        declared_scm_identities,
    ) in specifications:
        body = {
            "family_id": family,
            "coordinate": maven_coordinate(
                group_id=group, artifact_id=artifact, version=version
            ),
            "requirement": CandidateRequirement.OPTIONAL,
            "expected_scm_repository": repository,
            "requested_scm_ref": ref,
            "repository_source_prefixes": prefixes,
            "java_release": M336B_TARGET_RELEASE,
            "metadata_pom_sha256": pom_hash,
            "source_content_length": length,
            "source_sha256_sidecar_available": sidecar,
            "source_signature_available": True,
            "declared_scm_identities": declared_scm_identities,
        }
        result.append(
            FrozenMavenSourceCandidate(**body, policy_hash=content_hash(body))
        )
    return tuple(result)


def acquire_and_qualify_maven_source_candidates(
    candidates: tuple[FrozenMavenSourceCandidate, ...],
    *,
    output_root: Path,
    acquired_at: str,
    host: str,
    acquisition_run_id: str,
    minimum_eligible_roots: int,
    policy_mode: AcquisitionPolicyMode,
    maven_provider: MavenCentralProvenanceProvider | None = None,
    scm_provider: ScmRevisionProvider | None = None,
) -> MavenCandidateAcquisitionResult:
    """The sole production path for disclosed rehearsal and fresh acquisition."""

    frozen = tuple(candidates)
    _verify_candidate_policy(frozen)
    if output_root.exists():
        raise FileExistsError("candidate acquisition output already exists")
    output_root.mkdir(parents=True)
    maven_provider = maven_provider or MavenCentralProvenanceProvider()
    scm_provider = scm_provider or ScmRevisionProvider()
    acquired = []
    override_count = 0
    for candidate in frozen:
        source = maven_provider.fetch_sources(candidate.coordinate)
        pom = maven_provider.fetch_pom(candidate.coordinate)
        if bytes_hash(pom.payload) != candidate.metadata_pom_sha256:
            raise ValueError("production POM differs from frozen metadata receipt")
        if len(source.payload) != candidate.source_content_length:
            raise ValueError("production source size differs from frozen HEAD metadata")
        if (
            source.digest.sidecar_verified
            is not candidate.source_sha256_sidecar_available
        ):
            raise ValueError("source SHA-256 sidecar availability changed after freeze")
        if (
            source.digest.detached_signature_url is not None
        ) is not candidate.source_signature_available:
            raise ValueError("source signature availability changed after freeze")
        pom_evidence = parse_maven_pom(pom.payload, candidate.coordinate)
        observed_scm = tuple(
            item for item in (pom_evidence.scm_connection, pom_evidence.scm_url) if item
        )
        if candidate.declared_scm_identities:
            if not set(candidate.declared_scm_identities).issubset(observed_scm):
                raise ValueError(
                    "POM SCM identity differs from frozen candidate policy"
                )
        elif observed_scm:
            expected = canonical_github_repository(candidate.expected_scm_repository)[0]
            if not any(
                canonical_github_repository(item)[0] == expected
                for item in observed_scm
            ):
                raise ValueError(
                    "POM SCM identity differs from frozen candidate policy"
                )
        inspection = inspect_source_archive(source.payload)
        scm = scm_provider.verify(
            repository_url=candidate.expected_scm_repository,
            requested_ref=candidate.requested_scm_ref,
        )
        correspondence = correspond_source_trees(
            inspection.java_entries,
            scm.java_entries,
            repository_path_prefixes=candidate.repository_source_prefixes,
        )
        scm_license = (
            license_text_evidence(
                f"SCM/{scm.license_entries[0][0]}", scm.license_entries[0][1]
            )
            if scm.license_entries
            else None
        )
        mode, license_status, conflicts = resolve_license_evidence(
            pom_claims=pom_evidence.licenses,
            embedded_texts=inspection.license_evidence,
            scm_text=scm_license,
            scm_revision_receipt=scm.receipt,
            correspondence=correspondence,
        )
        audit = build_provenance_audit_event(
            acquired_at=acquired_at,
            host=host,
            acquisition_run_id=acquisition_run_id,
            network_receipt_hashes=(
                source.repository.network_receipt_hash,
                pom.repository.network_receipt_hash,
                scm.receipt.remote_ref_response_hash,
                scm.receipt.commit_retrieval_response_hash,
            ),
        )
        envelope = build_provenance_envelope(
            schema_version=SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION,
            coordinate=candidate.coordinate,
            artifact_digest=source.digest,
            repository_metadata=source.repository,
            pom_digest=pom.digest,
            pom_repository_metadata=pom.repository,
            license_claims=pom_evidence.licenses,
            license_texts=(
                *inspection.license_evidence,
                *((scm_license,) if scm_license else ()),
            ),
            license_evidence_mode=mode,
            license_status=license_status,
            scm_revision=scm.receipt,
            correspondence=correspondence,
            conflicts=conflicts,
            audit_event=audit,
        )
        verify_source_artifact_provenance_envelope(
            envelope, artifact_bytes=source.payload, pom_bytes=pom.payload
        )
        paths = tuple(path for path, _raw in inspection.java_entries)
        raw_hashes = tuple(
            sorted(bytes_hash(raw) for _path, raw in inspection.java_entries)
        )
        canonical_hashes = tuple(
            sorted(
                bytes_hash(canonical_source_bytes(raw))
                for _path, raw in inspection.java_entries
            )
        )
        coordinate_text = (
            f"{candidate.coordinate.namespace}:{candidate.coordinate.name}:"
            f"{candidate.coordinate.version}"
        )
        disclosed = match_disclosed_material(
            coordinate=coordinate_text,
            archive_hash=source.digest.downloaded_bytes_sha256,
            source_url=source.repository.requested_url,
            pom_hash=pom.digest.downloaded_bytes_sha256,
            raw_source_hashes=raw_hashes,
            canonical_source_hashes=canonical_hashes,
            source_tree_hash=scm.receipt.source_tree_hash,
            selected_path_manifest_hash=content_hash(paths),
            scm_revision=scm.receipt.immutable_commit,
            correspondence_hash=correspondence.correspondence_hash,
        )
        override = (
            policy_mode is AcquisitionPolicyMode.DEVELOPMENT_DISCLOSED_REHEARSAL
            and disclosed.denied
        )
        override_count += int(override)
        root = output_root / "roots" / candidate.family_id
        _write_source_root(root, inspection.java_entries)
        decision = qualify_artifact(
            envelope,
            requirement=candidate.requirement,
            eligible_root=str(root.resolve()),
            denied=disclosed.denied and not override,
            release_compatible=candidate.java_release == M336B_TARGET_RELEASE,
        )
        verify_artifact_qualification_decision(
            decision,
            envelope=envelope,
            requirement=candidate.requirement,
            expected_coordinate=candidate.coordinate,
        )
        candidate_root = output_root / "candidates" / candidate.family_id
        candidate_root.mkdir(parents=True)
        (candidate_root / "source.jar").write_bytes(source.payload)
        (candidate_root / "pom.xml").write_bytes(pom.payload)
        (candidate_root / "scm.zip").write_bytes(scm.archive_payload)
        (candidate_root / "provenance.json").write_bytes(
            dump_source_artifact_provenance_envelope(envelope)
        )
        _write_json(candidate_root / "qualification.json", asdict(decision))
        _write_json(candidate_root / "disclosed_match.json", asdict(disclosed))
        acquired.append(
            AcquiredMavenSourceCandidate(
                candidate,
                envelope,
                decision,
                disclosed,
                root,
                inspection,
                source.payload,
                pom.payload,
                scm.archive_payload,
                raw_hashes,
                canonical_hashes,
            )
        )
    decisions = tuple(item.qualification for item in acquired)
    envelopes = tuple(item.envelope for item in acquired)
    qualification = qualify_candidate_set(
        decisions, minimum_eligible_roots=minimum_eligible_roots
    )
    verify_candidate_qualification_set(
        qualification,
        candidates=frozen,
        decisions=decisions,
        envelopes=envelopes,
        minimum_eligible_roots=minimum_eligible_roots,
    )
    report_body = {
        "policy_version": M336B_CANDIDATE_POLICY_VERSION,
        "policy_mode": policy_mode,
        "candidate_policy_hashes": tuple(item.policy_hash for item in frozen),
        "envelope_hashes": tuple(item.envelope.envelope_hash for item in acquired),
        "decision_hashes": tuple(item.qualification.decision_hash for item in acquired),
        "qualification_set_hash": qualification["qualification_set_hash"],
        "selector_invocation_count": 0,
        "selector_rerun_count": 0,
        "development_denylist_override_count": override_count,
    }
    report_hash = content_hash(report_body)
    _write_json(
        output_root / "acquisition_report.json",
        {**report_body, "report_hash": report_hash},
    )
    _write_json(output_root / "qualification_set.json", qualification)
    return MavenCandidateAcquisitionResult(
        policy_version=M336B_CANDIDATE_POLICY_VERSION,
        policy_mode=policy_mode,
        candidates=tuple(acquired),
        qualification_set=qualification,
        selector_invocation_count=0,
        selector_rerun_count=0,
        development_denylist_override_count=override_count,
        report_hash=report_hash,
    )


def _verify_candidate_policy(candidates):
    if not candidates:
        raise ValueError("candidate policy denominator is empty")
    coordinates = tuple(item.coordinate for item in candidates)
    families = tuple(item.family_id for item in candidates)
    if len(set(coordinates)) != len(coordinates) or len(set(families)) != len(families):
        raise ValueError("candidate policy identities must be unique")
    for item in candidates:
        body = asdict(item)
        claimed = body.pop("policy_hash")
        if (
            item.requirement is not CandidateRequirement.OPTIONAL
            or item.java_release != M336B_TARGET_RELEASE
            or content_hash(body) != claimed
        ):
            raise ValueError("candidate policy is not frozen or optional")


def _write_source_root(root: Path, entries):
    if root.exists():
        raise FileExistsError("candidate source root already exists")
    root.mkdir(parents=True)
    for relative, raw in entries:
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("candidate source path is unsafe")
        destination = root.joinpath(*path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
