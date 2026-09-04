"""Strict Maven Central adapter for generic source-artifact provenance."""

from __future__ import annotations

import io
import re
import stat
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    ArtifactDigestEvidence,
    LicenseClaim,
    LicenseEvidenceMode,
    LicenseTextEvidence,
    ProvenanceStatus,
    RepositoryMetadataEvidence,
    SourceArtifactCoordinate,
    SourceCorrespondenceStatus,
    SourceTreeCorrespondence,
    SourceTreeCorrespondenceEntry,
)

MAVEN_CENTRAL_HOSTS = frozenset({"repo.maven.apache.org"})
APACHE_2_LICENSE_RAW_SHA256 = (
    "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
)
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LICENSE_NAMES = frozenset({"license", "license.txt", "license.md"})


@dataclass(frozen=True)
class MavenPomEvidence:
    coordinate: SourceArtifactCoordinate
    licenses: tuple[LicenseClaim, ...]
    scm_connection: str | None
    scm_url: str | None
    pom_sha256: str
    evidence_hash: str


@dataclass(frozen=True)
class ArchiveInspection:
    java_entries: tuple[tuple[str, bytes], ...]
    license_evidence: tuple[LicenseTextEvidence, ...]
    archive_tree_hash: str
    entry_count: int
    total_uncompressed_bytes: int
    inspection_hash: str


@dataclass(frozen=True)
class FetchedMavenComponent:
    payload: bytes
    digest: ArtifactDigestEvidence
    repository: RepositoryMetadataEvidence


class _StrictRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, chain: list[str]):
        self.chain = chain

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in MAVEN_CENTRAL_HOSTS:
            raise ValueError("repository redirect left the frozen host allowlist")
        self.chain.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MavenCentralProvenanceProvider:
    """Fetch only coordinate-derived Maven Central locations; never POM-provided URLs."""

    def __init__(self, *, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds

    def fetch_sources(
        self, coordinate: SourceArtifactCoordinate
    ) -> FetchedMavenComponent:
        return self._fetch_component(coordinate, coordinate.canonical_repository_path)

    def fetch_pom(self, coordinate: SourceArtifactCoordinate) -> FetchedMavenComponent:
        prefix = coordinate.canonical_repository_path.rsplit("/", 1)[0]
        name = f"{coordinate.name}-{coordinate.version}.pom"
        return self._fetch_component(
            coordinate, f"{prefix}/{name}", source_coordinate=False
        )

    def _fetch_component(self, coordinate, component_path, *, source_coordinate=True):
        url = f"{coordinate.repository}/{component_path}"
        chain: list[str] = []
        opener = urllib.request.build_opener(_StrictRedirectHandler(chain))
        request = urllib.request.Request(
            url, headers={"User-Agent": "ai-brain-source-provenance/1"}
        )
        with opener.open(request, timeout=self.timeout_seconds) as response:
            payload = response.read()
            final_url = response.geturl()
            headers = response.headers
        if source_coordinate:
            validate_repository_exchange(
                coordinate,
                requested_url=url,
                final_url=final_url,
                redirect_chain=tuple(chain),
            )
        else:
            _validate_component_url(url, final_url, chain)
        sidecar = self._optional_fetch(opener, f"{url}.sha256")
        signature = self._optional_fetch(opener, f"{url}.asc")
        if sidecar is None:
            digest = bytes_hash(payload)
            sidecar_verified = False
        else:
            digest = verify_sha256_sidecar(payload, sidecar)
            sidecar_verified = True
        content_length = headers.get("Content-Length")
        if content_length is not None and int(content_length) != len(payload):
            raise ValueError("Maven response content length mismatch")
        network_body = {
            "requested_url": url,
            "final_url": final_url,
            "redirect_chain": tuple(chain),
            "content_length": len(payload),
            "media_type": headers.get_content_type(),
        }
        repository = RepositoryMetadataEvidence(
            repository_host=urllib.parse.urlsplit(final_url).hostname or "",
            network_receipt_hash=content_hash(network_body),
            **network_body,
        )
        digest_evidence = ArtifactDigestEvidence(
            downloaded_bytes_sha256=digest,
            sidecar_sha256=digest if sidecar is not None else None,
            sidecar_verified=sidecar_verified,
            detached_signature_url=f"{url}.asc" if signature is not None else None,
            artifact_size=len(payload),
        )
        return FetchedMavenComponent(payload, digest_evidence, repository)

    def _optional_fetch(self, opener, url):
        try:
            with opener.open(
                urllib.request.Request(
                    url, headers={"User-Agent": "ai-brain-source-provenance/1"}
                ),
                timeout=self.timeout_seconds,
            ) as response:
                _validate_component_url(url, response.geturl(), ())
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise


def maven_coordinate(
    *,
    group_id: str,
    artifact_id: str,
    version: str,
    classifier: str = "sources",
    extension: str = "jar",
    repository: str = "https://repo.maven.apache.org/maven2",
) -> SourceArtifactCoordinate:
    for label, value in (
        ("group", group_id),
        ("artifact", artifact_id),
        ("version", version),
        ("classifier", classifier),
        ("extension", extension),
    ):
        if not value or any(char in value for char in "/\\?#"):
            raise ValueError(f"unsafe Maven {label}")
    name = f"{artifact_id}-{version}-{classifier}.{extension}"
    path = f"{group_id.replace('.', '/')}/{artifact_id}/{version}/{name}"
    parsed = urllib.parse.urlsplit(repository)
    if parsed.scheme != "https" or parsed.hostname not in MAVEN_CENTRAL_HOSTS:
        raise ValueError("repository is outside the frozen Maven Central allowlist")
    if classifier != "sources" or extension != "jar":
        raise ValueError("unexpected Maven source artifact classifier or extension")
    return SourceArtifactCoordinate(
        repository=repository.rstrip("/"),
        namespace=group_id,
        name=artifact_id,
        version=version,
        classifier=classifier,
        extension=extension,
        canonical_repository_path=path,
    )


def validate_repository_exchange(
    coordinate: SourceArtifactCoordinate,
    *,
    requested_url: str,
    final_url: str,
    redirect_chain=(),
) -> None:
    expected = f"{coordinate.repository}/{coordinate.canonical_repository_path}"
    if requested_url != expected:
        raise ValueError("requested URL does not match the frozen GAV path")
    for value in (requested_url, *redirect_chain, final_url):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != "https":
            raise ValueError("repository exchange attempted an HTTP downgrade")
        if parsed.hostname not in MAVEN_CENTRAL_HOSTS:
            raise ValueError("repository exchange left the frozen host allowlist")
    if final_url != expected:
        raise ValueError("final URL does not match the frozen GAV path")


def verify_sha256_sidecar(payload: bytes, sidecar: bytes | None) -> str:
    if sidecar is None:
        raise ValueError("required SHA-256 sidecar is missing")
    try:
        text = sidecar.decode("ascii", errors="strict").strip().casefold()
    except UnicodeDecodeError as exc:
        raise ValueError("malformed SHA-256 sidecar") from exc
    fields = text.split()
    if not fields or not _HASH.fullmatch(fields[0]) or len(fields) > 2:
        raise ValueError("malformed SHA-256 sidecar")
    expected = fields[0]
    actual = bytes_hash(payload)
    if expected != actual:
        raise ValueError("SHA-256 sidecar mismatch")
    return actual


def parse_maven_pom(
    raw: bytes, coordinate: SourceArtifactCoordinate
) -> MavenPomEvidence:
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Maven POM DTD and external entities are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("malformed Maven POM XML") from exc
    if _local(root.tag) != "project":
        raise ValueError("Maven POM root must be project")

    def children(parent, name):
        return tuple(child for child in parent if _local(child.tag) == name)

    def one(parent, name, *, required=False):
        values = children(parent, name)
        if len(values) > 1:
            raise ValueError(f"duplicate Maven POM {name}")
        if not values:
            if required:
                raise ValueError(f"missing Maven POM {name}")
            return None
        return (values[0].text or "").strip() or None

    parents = children(root, "parent")
    if len(parents) > 1:
        raise ValueError("duplicate Maven POM parent")
    parent = parents[0] if parents else None
    group = one(root, "groupId") or (
        one(parent, "groupId") if parent is not None else None
    )
    artifact = one(root, "artifactId", required=True)
    version = one(root, "version") or (
        one(parent, "version") if parent is not None else None
    )
    if (group, artifact, version) != (
        coordinate.namespace,
        coordinate.name,
        coordinate.version,
    ):
        raise ValueError("Maven POM GAV does not match the frozen coordinate")
    license_parents = children(root, "licenses")
    if len(license_parents) > 1:
        raise ValueError("duplicate Maven POM licenses metadata")
    claims = []
    if license_parents:
        for node in children(license_parents[0], "license"):
            name = one(node, "name", required=True)
            url = one(node, "url") or ""
            spdx = _apache_spdx(name, url)
            body = {
                "spdx_identifier": spdx,
                "declaration_source": "MAVEN_POM",
                "declared_name": name,
            }
            claims.append(LicenseClaim(**body, declaration_hash=content_hash(body)))
    scm_nodes = children(root, "scm")
    if len(scm_nodes) > 1:
        raise ValueError("duplicate Maven POM SCM metadata")
    connection = one(scm_nodes[0], "connection") if scm_nodes else None
    scm_url = one(scm_nodes[0], "url") if scm_nodes else None
    body = {
        "coordinate": coordinate,
        "licenses": tuple(claims),
        "scm_connection": connection,
        "scm_url": scm_url,
        "pom_sha256": bytes_hash(raw),
    }
    return MavenPomEvidence(**body, evidence_hash=content_hash(body))


def normalize_license_text(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("malformed license encoding") from exc
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return (
        "\n".join(line.rstrip() for line in text.split("\n")).rstrip() + "\n"
    ).encode()


def apache_2_license_identity() -> str:
    # Apache publishes one canonical text; the frozen raw bytes used by the three
    # disclosed candidates already have LF, UTF-8 and no trailing whitespace.
    return APACHE_2_LICENSE_RAW_SHA256


def license_text_evidence(path: str, raw: bytes) -> LicenseTextEvidence:
    normalized = normalize_license_text(raw)
    digest = bytes_hash(normalized)
    return LicenseTextEvidence(
        evidence_path=_canonical_archive_path(path),
        raw_text_sha256=bytes_hash(raw),
        normalized_text_sha256=digest,
        canonical_license_sha256=apache_2_license_identity(),
        exact_match=digest == apache_2_license_identity(),
    )


def inspect_source_archive(raw: bytes) -> ArchiveInspection:
    try:
        opened = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("malformed source archive") from exc
    infos = opened.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ValueError("source archive entry limit exceeded")
    seen = set()
    folded = set()
    total = 0
    java_entries = []
    license_entries = []
    for info in infos:
        path = _canonical_archive_path(info.filename)
        collision = unicodedata.normalize("NFC", path).casefold()
        if path in seen:
            raise ValueError("duplicate ZIP path")
        if collision in folded:
            raise ValueError("NFC/casefold ZIP path collision")
        seen.add(path)
        folded.add(collision)
        if info.flag_bits & 0x1:
            raise ValueError("encrypted ZIP entry")
        mode = info.external_attr >> 16
        if stat.S_IFMT(mode) == stat.S_IFLNK:
            raise ValueError("symlink ZIP entry")
        if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
            raise ValueError("source archive entry size limit exceeded")
        total += info.file_size
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError("source archive uncompressed-size limit exceeded")
        if info.file_size and info.compress_size == 0:
            raise ValueError("source archive compression ratio is invalid")
        if (
            info.compress_size
            and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise ValueError("source archive compression ratio limit exceeded")
        if info.is_dir():
            continue
        payload = opened.read(info)
        if path.endswith(".java"):
            java_entries.append((path, payload))
        parts = PurePosixPath(path).parts
        if len(parts) <= 2 and PurePosixPath(path).name.casefold() in _LICENSE_NAMES:
            license_entries.append((path, payload))
    opened.close()
    licenses = tuple(
        license_text_evidence(path, value) for path, value in license_entries
    )
    identities = {item.normalized_text_sha256 for item in licenses}
    if len(identities) > 1:
        raise ValueError("multiple conflicting license files")
    rows = tuple(
        (path, bytes_hash(value), len(value)) for path, value in sorted(java_entries)
    )
    tree_hash = content_hash(rows)
    body = {
        "java_entry_manifest": rows,
        "license_evidence": licenses,
        "archive_tree_hash": tree_hash,
        "entry_count": len(infos),
        "total_uncompressed_bytes": total,
    }
    return ArchiveInspection(
        java_entries=tuple(sorted(java_entries)),
        license_evidence=licenses,
        archive_tree_hash=tree_hash,
        entry_count=len(infos),
        total_uncompressed_bytes=total,
        inspection_hash=content_hash(body),
    )


def correspond_source_trees(
    artifact_java, repository_java, *, repository_path_prefixes: tuple[str, ...] = ()
) -> SourceTreeCorrespondence:
    artifact = tuple(
        (_canonical_archive_path(path), value) for path, value in artifact_java
    )
    prefixes = tuple(
        _canonical_archive_path(item).rstrip("/") + "/"
        for item in repository_path_prefixes
    )
    repository = tuple(
        (_canonical_archive_path(path), value)
        for path, value in repository_java
        if not prefixes or _canonical_archive_path(path).startswith(prefixes)
    )
    by_hash = {}
    for path, raw in repository:
        by_hash.setdefault(bytes_hash(canonical_source_bytes(raw)), []).append(
            (path, raw)
        )
    entries = []
    for path, raw in sorted(artifact):
        raw_hash = bytes_hash(raw)
        canonical_hash = bytes_hash(canonical_source_bytes(raw))
        matches = by_hash.get(canonical_hash, ())
        same_path = tuple(item for item in matches if item[0].endswith(path))
        if len(same_path) == 1:
            target, _ = same_path[0]
            status = SourceCorrespondenceStatus.EXACT_MATCH
        elif len(matches) == 1:
            target, _ = matches[0]
            status = SourceCorrespondenceStatus.PATH_RELOCATED_EXACT_CONTENT
        elif not matches:
            target = None
            status = SourceCorrespondenceStatus.UNMATCHED
        else:
            target = None
            status = SourceCorrespondenceStatus.AMBIGUOUS_MATCH
        body = {
            "artifact_path": path,
            "repository_path": target,
            "raw_sha256": raw_hash,
            "canonical_sha256": canonical_hash,
            "status": status,
        }
        entries.append(
            SourceTreeCorrespondenceEntry(**body, entry_hash=content_hash(body))
        )
    counts = {
        status: sum(item.status is status for item in entries)
        for status in SourceCorrespondenceStatus
    }
    eligible = sum(
        item.status
        in {
            SourceCorrespondenceStatus.EXACT_MATCH,
            SourceCorrespondenceStatus.PATH_RELOCATED_EXACT_CONTENT,
            SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
        }
        for item in entries
    )
    body = {
        "entries": tuple(entries),
        "exact_match_count": counts[SourceCorrespondenceStatus.EXACT_MATCH],
        "relocated_match_count": counts[
            SourceCorrespondenceStatus.PATH_RELOCATED_EXACT_CONTENT
        ],
        "generated_match_count": counts[
            SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE
        ],
        "unmatched_count": counts[SourceCorrespondenceStatus.UNMATCHED],
        "ambiguous_count": counts[SourceCorrespondenceStatus.AMBIGUOUS_MATCH],
        "eligible_entry_count": eligible,
    }
    return SourceTreeCorrespondence(**body, correspondence_hash=content_hash(body))


def resolve_license_evidence(
    *,
    pom_claims: tuple[LicenseClaim, ...],
    embedded_texts: tuple[LicenseTextEvidence, ...],
    scm_text: LicenseTextEvidence | None,
    immutable_scm_verified: bool,
    correspondence: SourceTreeCorrespondence | None,
) -> tuple[LicenseEvidenceMode, ProvenanceStatus, tuple[str, ...]]:
    pom_values = {item.spdx_identifier for item in pom_claims}
    embedded_exact = bool(embedded_texts) and all(
        item.exact_match for item in embedded_texts
    )
    scm_exact = bool(scm_text and scm_text.exact_match and immutable_scm_verified)
    pom_apache = pom_values == {"Apache-2.0"}
    conflicts = []
    if pom_values and pom_values != {"Apache-2.0"}:
        conflicts.append("POM_LICENSE_CONFLICT")
    if embedded_texts and not embedded_exact:
        conflicts.append("EMBEDDED_LICENSE_CONFLICT")
    if scm_text and not scm_text.exact_match:
        conflicts.append("SCM_LICENSE_CONFLICT")
    if conflicts:
        return (
            LicenseEvidenceMode.CONFLICTING_LICENSE_EVIDENCE,
            ProvenanceStatus.CONFLICT,
            tuple(conflicts),
        )
    complete_correspondence = bool(
        correspondence
        and not correspondence.unmatched_count
        and not correspondence.ambiguous_count
        and correspondence.eligible_entry_count
    )
    if embedded_exact and pom_apache and scm_exact and complete_correspondence:
        return (
            LicenseEvidenceMode.EMBEDDED_AND_SCM_CORROBORATED,
            ProvenanceStatus.VERIFIED,
            (),
        )
    if embedded_exact:
        return LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE, ProvenanceStatus.VERIFIED, ()
    if pom_apache and scm_exact and complete_correspondence:
        return (
            LicenseEvidenceMode.POM_PLUS_IMMUTABLE_SCM_LICENSE,
            ProvenanceStatus.VERIFIED,
            (),
        )
    if pom_apache:
        return (
            LicenseEvidenceMode.POM_DECLARATION_ONLY,
            ProvenanceStatus.REVIEW_REQUIRED,
            (),
        )
    return LicenseEvidenceMode.NO_LICENSE_EVIDENCE, ProvenanceStatus.INELIGIBLE, ()


def canonical_source_bytes(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("malformed Java source encoding") from exc
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return (text.rstrip() + "\n").encode()


def _canonical_archive_path(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/"))
    if (
        not normalized
        or normalized.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise ValueError("source archive contains an absolute path")
    path = PurePosixPath(normalized)
    if any(
        part in {"", ".", ".."} for part in path.parts
    ) or path.as_posix() != normalized.rstrip("/"):
        raise ValueError(
            "source archive contains path traversal or a non-canonical path"
        )
    return normalized.rstrip("/")


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _apache_spdx(name: str, url: str) -> str:
    normalized = f"{name} {url}".casefold()
    if "apache" in normalized and ("2.0" in normalized or "license-2.0" in normalized):
        return "Apache-2.0"
    return "UNKNOWN"


def _validate_component_url(requested_url: str, final_url: str, redirect_chain) -> None:
    for value in (requested_url, *redirect_chain, final_url):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in MAVEN_CENTRAL_HOSTS:
            raise ValueError("Maven component exchange left the frozen allowlist")
    if requested_url != final_url:
        raise ValueError("Maven component final URL changed")
