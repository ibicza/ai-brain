"""Disclosed-only M-33.6c qualification and selector preparation."""

from __future__ import annotations

import io
import json
import time
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_source_selector import (
    JavaFinalSourceSelectorPolicy,
    frozen_m336b_final_source_selector_policy,
    m336b_selector_receipt,
    select_final_java_sources,
)
from ai_brain.stage3.acquisition.m336b_provenance import frozen_m336b_candidate_pool
from ai_brain.stage3.acquisition.maven_provenance import (
    canonical_source_bytes,
    inspect_source_archive,
    parse_maven_pom,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    DetachedSignatureStatus,
    load_source_artifact_provenance_envelope,
    verify_source_artifact_provenance_envelope,
)
from ai_brain.stage3.acquisition.source_authority import (
    CandidateEligibleSourceSet,
    KnowledgeAcquisitionEligibility,
    PublicationTarget,
    SourceAuthorityDecision,
    SourceUseAuthorizationReceipt,
    SourceUseScope,
    build_candidate_eligible_source_set,
    build_source_authority_decision,
    build_source_use_authorization,
    classify_source_authenticity,
    fuse_license_evidence,
)
from ai_brain.stage3.acquisition.spdx_license import (
    LicenseConflictClassification,
    LicenseDocumentRole,
    SPDXLicenseMatcher,
    SPDXLicenseMatchReceipt,
    classify_license_difference,
    classify_license_document,
    first_differing_span,
)

M336C_BASE_SHA = "1541805f9cd6c19ff9c372afeefbd41148217736"
M336C_AUTHORITY_POLICY_VERSION = "m336c.task-supplied-source-use.v1"
_DOCUMENT_NAMES = frozenset(
    {
        "license",
        "license.txt",
        "license.md",
        "copying",
        "copying.txt",
        "notice",
        "notice.txt",
        "notice.md",
        "notice-docs",
        "dependencies",
    }
)


@dataclass(frozen=True)
class LicenseDocumentForensics:
    container: str
    path: str
    role: LicenseDocumentRole
    raw_sha256: str
    canonical_sha256: str
    match_receipt: SPDXLicenseMatchReceipt


@dataclass(frozen=True)
class CandidateLicenseConflictForensics:
    historical_reason: str
    classification: LicenseConflictClassification
    first_differing_span: dict[str, object]
    required_clause_differences: tuple[str, ...]
    optional_section_differences: tuple[str, ...]
    replaceable_text_differences: tuple[str, ...]
    whitespace_or_punctuation_differences: tuple[str, ...]
    additional_substantive_clauses: tuple[str, ...]
    missing_substantive_clauses: tuple[str, ...]
    spdx_template_result: str
    independent_reference_result: str


@dataclass(frozen=True)
class DisclosedCandidateAssessment:
    family_id: str
    coordinate: str
    source_jar_sha256: str
    pom_sha256: str
    pom_license_declarations: tuple[str, ...]
    pom_scm_metadata: tuple[str, ...]
    immutable_scm_commit: str
    source_tree_hash: str
    correspondence_hash: str
    documents: tuple[LicenseDocumentForensics, ...]
    historical_qualification: str
    conflict_forensics: CandidateLicenseConflictForensics | None
    eligible_source_set: CandidateEligibleSourceSet
    authority: SourceAuthorityDecision
    assessment_hash: str


@dataclass(frozen=True)
class DisclosedPreparation:
    assessments: tuple[DisclosedCandidateAssessment, ...]
    authorization: SourceUseAuthorizationReceipt
    selector_policy: JavaFinalSourceSelectorPolicy
    selector_receipt: dict
    roots: tuple[tuple[str, Path], ...]
    selected_sources: tuple[Path, ...]
    report_hash: str


def m336c_source_use_authorization() -> SourceUseAuthorizationReceipt:
    return build_source_use_authorization(
        authority_kind="TASK_SUPPLIED_POLICY",
        authority_id="M-33.6c disclosed-development corpus instruction",
        authorized_scopes=(
            SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
            SourceUseScope.LOCAL_RESEARCH_EVALUATION,
            SourceUseScope.DERIVED_KNOWLEDGE_ONLY,
            SourceUseScope.RAW_SOURCE_RETENTION,
        ),
        publication_targets=(
            PublicationTarget.DERIVED_PACK_PUBLICATION,
            PublicationTarget.METRICS_ONLY_PUBLICATION,
        ),
        policy_version=M336C_AUTHORITY_POLICY_VERSION,
    )


def disclosed_rehearsal_selector_policy() -> JavaFinalSourceSelectorPolicy:
    """Reuse the H17 policy shape for disclosed development; this is not a final seed."""

    original = frozen_m336b_final_source_selector_policy()
    interim = replace(
        original,
        maximum_files=120,
        prior_corpus_hash_denylist=(),
        selection_strategy=(
            original.selection_strategy
            + "; disclosed-development replay anchored to historical E17, never a final freeze"
        ),
        policy_hash="",
    )
    body = asdict(interim)
    body.pop("policy_hash")
    return replace(interim, policy_hash=content_hash(body))


def prepare_disclosed_rehearsal(
    *,
    disclosed_root: Path,
    work_root: Path,
    selected_root: Path,
    performance_samples: dict[str, list[float]] | None = None,
) -> DisclosedPreparation:
    if work_root.exists() or selected_root.exists():
        raise FileExistsError("M-33.6c disclosed preparation outputs already exist")
    work_root.mkdir(parents=True)
    selected_root.mkdir(parents=True)
    matcher = SPDXLicenseMatcher()
    authorization = m336c_source_use_authorization()
    policies = {item.family_id: item for item in frozen_m336b_candidate_pool()}
    assessments = []
    roots = []
    for family_dir in sorted(
        (item for item in disclosed_root.iterdir() if item.is_dir()),
        key=lambda item: item.name,
    ):
        policy = policies.get(family_dir.name)
        if policy is None:
            raise ValueError("disclosed bundle contains an unknown candidate family")
        assessment, java_entries = assess_disclosed_candidate(
            family_dir,
            policy,
            matcher=matcher,
            authorization=authorization,
            performance_samples=performance_samples,
        )
        assessments.append(assessment)
        if (
            assessment.authority.knowledge_acquisition
            is KnowledgeAcquisitionEligibility.ELIGIBLE_FOR_ANALYSIS
        ):
            root = work_root / family_dir.name
            root.mkdir()
            included = {
                item.artifact_path
                for item in assessment.eligible_source_set.entries
                if item.included
            }
            for relative, raw in java_entries:
                if relative not in included:
                    continue
                destination = _safe_destination(root, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            roots.append((family_dir.name, root))
    if len(assessments) != len(policies):
        raise ValueError("disclosed bundle candidate denominator mismatch")
    ordered_roots = tuple(sorted(roots))
    policy = disclosed_rehearsal_selector_policy()
    selected = select_final_java_sources(
        ordered_roots, f13_sha=M336C_BASE_SHA, policy=policy
    )
    selector = m336b_selector_receipt(policy, selected, ordered_roots, M336C_BASE_SHA)
    copied = []
    root_map = dict(ordered_roots)
    for source in selected:
        matches = tuple(
            (family, root)
            for family, root in ordered_roots
            if source.resolve().is_relative_to(root.resolve())
        )
        if len(matches) != 1:
            raise ValueError("selected source ownership is ambiguous")
        family, root = matches[0]
        destination = selected_root / family / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.append(destination)
    if set(root_map) != {path.relative_to(selected_root).parts[0] for path in copied}:
        raise ValueError("selector omitted an analysis-eligible disclosed root")
    report_body = {
        "assessment_hashes": tuple(item.assessment_hash for item in assessments),
        "authorization_receipt_hash": authorization.receipt_hash,
        "selector_policy_hash": policy.policy_hash,
        "selector_receipt_hash": selector["receipt_hash"],
        "analysis_eligible_root_count": len(ordered_roots),
        "selected_source_count": len(copied),
    }
    return DisclosedPreparation(
        assessments=tuple(assessments),
        authorization=authorization,
        selector_policy=policy,
        selector_receipt=selector,
        roots=ordered_roots,
        selected_sources=tuple(copied),
        report_hash=content_hash(report_body),
    )


def assess_disclosed_candidate(
    family_dir,
    policy,
    *,
    matcher: SPDXLicenseMatcher,
    authorization: SourceUseAuthorizationReceipt,
    performance_samples: dict[str, list[float]] | None = None,
):
    qualification_started = time.perf_counter()
    source_jar = (family_dir / "source.jar").read_bytes()
    pom = (family_dir / "pom.xml").read_bytes()
    scm_zip = (family_dir / "scm.zip").read_bytes()
    envelope = load_source_artifact_provenance_envelope(
        (family_dir / "provenance.json").read_bytes()
    )
    verify_source_artifact_provenance_envelope(
        envelope, artifact_bytes=source_jar, pom_bytes=pom
    )
    if (
        envelope.coordinate != policy.coordinate
        or envelope.scm_revision is None
        or envelope.correspondence is None
    ):
        raise ValueError("historical disclosed provenance identity mismatch")
    pom_evidence = parse_maven_pom(pom, policy.coordinate)
    inspection = inspect_source_archive(source_jar)
    documents = tuple(
        sorted(
            (
                *_inspect_license_documents(source_jar, "source.jar", matcher),
                *_inspect_license_documents(scm_zip, "scm.zip", matcher),
            ),
            key=lambda item: (item.container, item.path),
        )
    )
    if any(
        item.role is LicenseDocumentRole.UNKNOWN_LICENSE_DOCUMENT for item in documents
    ):
        raise ValueError("license document role remains unresolved")
    authenticity = classify_source_authenticity(envelope.artifact_authenticity_mode)
    authenticated_archive = envelope.artifact_digest.sidecar_verified or (
        envelope.artifact_digest.detached_signature_status
        is DetachedSignatureStatus.VERIFIED
    )
    eligibility_started = time.perf_counter()
    eligible_set = build_candidate_eligible_source_set(
        envelope.correspondence,
        authenticity=authenticity,
        authorization=authorization,
        authenticated_archive=authenticated_archive,
    )
    if performance_samples is not None:
        performance_samples.setdefault("entry_eligibility", []).append(
            time.perf_counter() - eligibility_started
        )
    fusion_started = time.perf_counter()
    fusion = fuse_license_evidence(
        pom_expressions=tuple(item.spdx_identifier for item in pom_evidence.licenses),
        document_receipts=tuple(item.match_receipt for item in documents),
        source_correspondence_complete=(
            eligible_set.analysis_eligible_entry_count == eligible_set.total_entry_count
        ),
    )
    if performance_samples is not None:
        performance_samples.setdefault("license_evidence_fusion", []).append(
            time.perf_counter() - fusion_started
        )
    authority = build_source_authority_decision(
        authenticity_mode=envelope.artifact_authenticity_mode,
        fusion=fusion,
        eligible_set=eligible_set,
        authorization=authorization,
    )
    historical = json.loads(
        (family_dir / "qualification.json").read_text(encoding="utf-8")
    )
    conflict = None
    if historical["status"] == "CONFLICT":
        scm_project = next(
            item
            for item in documents
            if item.container == "scm.zip"
            and item.role is LicenseDocumentRole.PROJECT_LICENSE
        )
        reference = matcher.snapshot_root.joinpath("Apache-2.0.txt").read_bytes()
        observed = _zip_read(scm_zip, scm_project.path)
        classification = classify_license_difference(scm_project.match_receipt)
        conflict = CandidateLicenseConflictForensics(
            historical_reason="SCM_LICENSE_CONFLICT",
            classification=classification,
            first_differing_span=first_differing_span(reference, observed),
            required_clause_differences=(),
            optional_section_differences=scm_project.match_receipt.accepted_optional_omissions,
            replaceable_text_differences=scm_project.match_receipt.accepted_replaceable_spans,
            whitespace_or_punctuation_differences=("NORMALIZED_LAYOUT_DIFFERS",),
            additional_substantive_clauses=(),
            missing_substantive_clauses=(),
            spdx_template_result=scm_project.match_receipt.match_status,
            independent_reference_result="TRUSTED_PROCESS_EXPECTED_APACHE_2_0",
        )
    coordinate = f"{policy.coordinate.namespace}:{policy.coordinate.name}:{policy.coordinate.version}"
    body = {
        "family_id": policy.family_id,
        "coordinate": coordinate,
        "source_jar_sha256": bytes_hash(source_jar),
        "pom_sha256": bytes_hash(pom),
        "pom_license_declarations": tuple(
            item.spdx_identifier for item in pom_evidence.licenses
        ),
        "pom_scm_metadata": tuple(
            item
            for item in (
                pom_evidence.scm_connection,
                pom_evidence.scm_url,
                pom_evidence.scm_tag,
            )
            if item
        ),
        "immutable_scm_commit": envelope.scm_revision.immutable_commit,
        "source_tree_hash": envelope.scm_revision.source_tree_hash,
        "correspondence_hash": envelope.correspondence.correspondence_hash,
        "documents": documents,
        "historical_qualification": historical["status"],
        "conflict_forensics": conflict,
        "eligible_source_set": eligible_set,
        "authority": authority,
    }
    if performance_samples is not None:
        performance_samples.setdefault("candidate_qualification", []).append(
            time.perf_counter() - qualification_started
        )
    return (
        DisclosedCandidateAssessment(**body, assessment_hash=content_hash(body)),
        inspection.java_entries,
    )


def _inspect_license_documents(raw_archive, container, matcher):
    result = []
    with zipfile.ZipFile(io.BytesIO(raw_archive)) as opened:
        for name in opened.namelist():
            if name.endswith("/") or not _is_license_document_path(name):
                continue
            raw = opened.read(name)
            role = classify_license_document(name)
            receipt = matcher.match(
                raw,
                source_document=f"{container}/{name}",
                document_role=role,
            )
            result.append(
                LicenseDocumentForensics(
                    container=container,
                    path=name,
                    role=role,
                    raw_sha256=bytes_hash(raw),
                    canonical_sha256=bytes_hash(canonical_source_bytes(raw)),
                    match_receipt=receipt,
                )
            )
    return tuple(result)


def _is_license_document_path(path: str) -> bool:
    name = PurePosixPath(path).name.casefold()
    return (
        name in _DOCUMENT_NAMES
        or name.startswith(("notice-", "third-party", "third_party"))
        or "licenseslashstarstyle" in name
    )


def _zip_read(raw_archive: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(raw_archive)) as opened:
        return opened.read(name)


def _safe_destination(root: Path, relative: str) -> Path:
    normalized = unicodedata.normalize("NFC", relative.replace("\\", "/"))
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("unsafe disclosed source path")
    destination = root.joinpath(*pure.parts)
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("disclosed source escaped its root")
    return destination


def dump_preparation_reports(preparation: DisclosedPreparation, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("source_use_authorization.json", preparation.authorization),
        ("candidate_authority.json", preparation.assessments),
        ("selector_receipt.json", preparation.selector_receipt),
    ):
        target = output / name
        target.write_text(
            canonical_json(
                asdict(value) if hasattr(value, "__dataclass_fields__") else value
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    conflicts = tuple(
        {
            "family_id": item.family_id,
            "coordinate": item.coordinate,
            "historical_qualification": item.historical_qualification,
            "conflict_forensics": asdict(item.conflict_forensics)
            if item.conflict_forensics
            else None,
            "documents": tuple(asdict(document) for document in item.documents),
        }
        for item in preparation.assessments
    )
    body = {
        "schema_version": 1,
        "candidate_count": len(preparation.assessments),
        "historical_conflict_count": sum(
            item.conflict_forensics is not None for item in preparation.assessments
        ),
        "unclassified_historical_conflict_count": sum(
            item.conflict_forensics is not None
            and item.conflict_forensics.classification
            is LicenseConflictClassification.UNRECOGNIZED_REVIEW_REQUIRED
            for item in preparation.assessments
        ),
        "unresolved_document_role_count": sum(
            document.role is LicenseDocumentRole.UNKNOWN_LICENSE_DOCUMENT
            for item in preparation.assessments
            for document in item.documents
        ),
        "candidates": conflicts,
    }
    (output / "license_forensics.json").write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
