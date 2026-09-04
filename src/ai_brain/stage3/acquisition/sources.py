"""Bounded offline source ingestion. No fetch, script, OCR, macro or archive path."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    normalize_datetime,
    utc_now,
)
from ai_brain.stage3.acquisition.models import (
    AcquisitionManifest,
    DocumentStructure,
    SourceBundle,
    SourceDocument,
    SourceMediaType,
)
from ai_brain.stage3.acquisition.version import (
    ACQUISITION_SCHEMA_VERSION,
    CANONICAL_ACQUISITION_SCHEMA_VERSION,
    CANONICAL_SOURCE_COMPILER_VERSION,
    LEGACY_SOURCE_COMPILER_VERSION,
    MAX_BUNDLE_BYTES,
    MAX_DOCUMENTS,
    MAX_FILE_BYTES,
    MAX_JSON_NESTING,
    MAX_LINE_BYTES,
    SOURCE_COMPILER_VERSION,
)

_EXTENSIONS = {
    ".txt": SourceMediaType.TEXT,
    ".md": SourceMediaType.MARKDOWN,
    ".markdown": SourceMediaType.MARKDOWN,
    ".html": SourceMediaType.HTML,
    ".htm": SourceMediaType.HTML,
    ".json": SourceMediaType.JSON,
    ".pdf": SourceMediaType.PDF,
    ".java": SourceMediaType.JAVA_SOURCE,
}
_RESOURCE_POLICY = {
    "file_bytes": MAX_FILE_BYTES,
    "bundle_bytes": MAX_BUNDLE_BYTES,
    "documents": MAX_DOCUMENTS,
    "line_bytes": MAX_LINE_BYTES,
    "json_nesting": MAX_JSON_NESTING,
    "network": False,
    "ocr": False,
    "javascript": False,
    "archives": False,
}


def ingest_bundle(
    paths: tuple[Path, ...],
    *,
    bundle_id: str,
    domain_tags: tuple[str, ...] = (),
    language: str = "en",
    imported_at: str | None = None,
    version: str = "1.0.0",
    source_root: Path | None = None,
    canonical_identity: bool | None = None,
    store=None,
) -> SourceBundle:
    if not bundle_id or not paths or len(paths) > MAX_DOCUMENTS:
        raise ValueError("source bundle identity or document count is invalid")
    if language not in {"ru", "en", "mixed"}:
        raise ValueError("unsupported source language")
    stamp = imported_at or utc_now()
    normalize_datetime(stamp)
    if any(path.is_symlink() for path in paths):
        raise ValueError("source symlink or non-file is forbidden")
    resolved = tuple(path.resolve(strict=True) for path in paths)
    if len(set(resolved)) != len(resolved):
        raise ValueError("duplicate source document")
    total = sum(path.stat().st_size for path in resolved)
    if total > MAX_BUNDLE_BYTES:
        raise ValueError("source bundle exceeds resource policy")
    resolved_root = source_root.resolve(strict=True) if source_root else None
    if resolved_root is not None and (
        not resolved_root.is_dir()
        or any(not path.is_relative_to(resolved_root) for path in resolved)
    ):
        raise ValueError("source root does not contain every source document")
    candidates = []
    original_relative_paths = []
    for path in resolved:
        if not path.is_file():
            raise ValueError("source symlink or non-file is forbidden")
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise ValueError("source document size is outside policy")
        original_relative_path = (
            path.relative_to(resolved_root).as_posix()
            if resolved_root is not None
            else path.name
        )
        original_relative_paths.append(original_relative_path)
        relative_path = _canonical_relative_path(
            original_relative_path, require_nfc=False
        )
        media = _media_type(path, raw)
        canonical = _canonical_text(raw, media)
        if any(
            len(line.encode("utf-8")) > MAX_LINE_BYTES
            for line in canonical.splitlines()
        ):
            raise ValueError("source line exceeds resource policy")
        raw_hash = bytes_hash(raw)
        text_hash = bytes_hash(canonical.encode("utf-8"))
        structure = _structure(canonical, media)
        candidates.append(
            (
                relative_path.encode("utf-8"),
                raw_hash,
                relative_path,
                raw,
                canonical,
                media,
                structure,
            )
        )
    if canonical_identity is not None and not isinstance(canonical_identity, bool):
        raise TypeError("canonical_identity must be bool or None")
    has_java = any(item[5] is SourceMediaType.JAVA_SOURCE for item in candidates)
    if canonical_identity and not has_java:
        raise ValueError("canonical identity v2 is currently defined for Java bundles")
    canonical_java = has_java and canonical_identity is not False
    if canonical_java:
        relative_paths = tuple(item[2] for item in candidates)
        if len(
            {unicodedata.normalize("NFC", item) for item in original_relative_paths}
        ) != len(original_relative_paths):
            raise ValueError("Unicode-normalization source path collision")
        if len(relative_paths) != len(set(relative_paths)):
            raise ValueError("duplicate normalized source path")
        if len({item.casefold() for item in relative_paths}) != len(relative_paths):
            raise ValueError("casefold source path collision")
        candidates.sort(key=lambda item: (item[0], item[1]))
    schema_version = (
        CANONICAL_ACQUISITION_SCHEMA_VERSION
        if canonical_java
        else ACQUISITION_SCHEMA_VERSION
    )
    compiler_version = (
        CANONICAL_SOURCE_COMPILER_VERSION if canonical_java else SOURCE_COMPILER_VERSION
    )
    documents = []
    for index, (
        _path_bytes,
        raw_hash,
        relative_path,
        raw,
        canonical,
        media,
        structure,
    ) in enumerate(candidates):
        text_hash = bytes_hash(canonical.encode("utf-8"))
        identity_body = {
            "schema_version": schema_version,
            "bundle_id": bundle_id,
            "relative_path": relative_path,
            "bytes_hash": raw_hash,
        }
        document_id = (
            f"{bundle_id}.document.{content_hash(identity_body)[:32]}"
            if canonical_java
            else f"{bundle_id}.document.{index + 1:03d}"
        )
        values = {
            "document_id": document_id,
            "media_type": media,
            "language": language,
            "relative_path": relative_path,
            "bytes_hash": raw_hash,
            "canonical_text_hash": text_hash,
            "source_metadata": (("original_name", relative_path),),
            "imported_at": stamp,
            "version": version,
            "parent_bundle_id": bundle_id,
            "structure": structure,
        }
        document = SourceDocument(
            **values,
            document_hash=content_hash(
                _document_semantic_body(values) if canonical_java else values
            ),
        )
        documents.append(document)
        if store is not None:
            store.put_blob(raw, expected_hash=raw_hash)
            store.put_blob(canonical.encode("utf-8"), expected_hash=text_hash)
    manifest_values = {
        "compiler_version": compiler_version,
        "resource_policy_hash": content_hash(_RESOURCE_POLICY),
        "runtime_network": False,
        "document_hashes": tuple(item.document_hash for item in documents),
        "schema_version": schema_version,
    }
    manifest = AcquisitionManifest(
        **manifest_values, manifest_hash=content_hash(manifest_values)
    )
    bundle_values = {
        "bundle_id": bundle_id,
        "domain_tags": (
            tuple(sorted(set(domain_tags)))
            if canonical_java
            else tuple(dict.fromkeys(domain_tags))
        ),
        "documents": tuple(documents),
        "manifest": manifest,
        "created_at": stamp,
    }
    bundle = SourceBundle(
        **bundle_values,
        bundle_hash=content_hash(
            _bundle_semantic_body(bundle_values) if canonical_java else bundle_values
        ),
    )
    verify_bundle(bundle, store=store)
    if store is not None:
        store.save_bundle(bundle)
    return bundle


def verify_bundle(bundle: SourceBundle, *, store=None) -> None:
    if bundle.manifest.schema_version not in {
        ACQUISITION_SCHEMA_VERSION,
        CANONICAL_ACQUISITION_SCHEMA_VERSION,
    }:
        raise ValueError("unsupported acquisition schema")
    legacy = bundle.manifest.schema_version == ACQUISITION_SCHEMA_VERSION
    expected_compiler = (
        LEGACY_SOURCE_COMPILER_VERSION if legacy else CANONICAL_SOURCE_COMPILER_VERSION
    )
    if (
        bundle.manifest.compiler_version != expected_compiler
        or bundle.manifest.runtime_network
    ):
        raise ValueError("unsupported or network-enabled acquisition manifest")
    if bundle.manifest.resource_policy_hash != content_hash(_RESOURCE_POLICY):
        raise ValueError("acquisition resource policy changed")
    if bundle.manifest.document_hashes != tuple(
        item.document_hash for item in bundle.documents
    ):
        raise ValueError("source bundle document manifest mismatch")
    manifest_body = asdict(bundle.manifest)
    manifest_digest = manifest_body.pop("manifest_hash")
    if content_hash(manifest_body) != manifest_digest:
        raise ValueError("acquisition manifest hash mismatch")
    if not legacy:
        _verify_canonical_java_bundle_shape(bundle)
    for document in bundle.documents:
        normalize_datetime(document.imported_at)
        body = asdict(document)
        digest = body.pop("document_hash")
        actual = content_hash(body if legacy else _document_semantic_body(body))
        if document.parent_bundle_id != bundle.bundle_id or actual != digest:
            raise ValueError("source document hash or parent mismatch")
        if store is not None:
            raw = store.get_blob(document.bytes_hash)
            canonical = store.get_blob(document.canonical_text_hash)
            if (
                bytes_hash(raw) != document.bytes_hash
                or bytes_hash(canonical) != document.canonical_text_hash
            ):
                raise ValueError("stored source bytes changed")
    normalize_datetime(bundle.created_at)
    body = asdict(bundle)
    digest = body.pop("bundle_hash")
    actual = content_hash(body if legacy else _bundle_semantic_body(body))
    if actual != digest:
        raise ValueError("source bundle hash mismatch")


def _verify_canonical_java_bundle_shape(bundle: SourceBundle) -> None:
    """Independently prove the v2 path, order, ID and tag invariants."""

    if not bundle.documents or any(
        item.media_type is not SourceMediaType.JAVA_SOURCE for item in bundle.documents
    ):
        raise ValueError("canonical Java bundle contains a non-Java document")
    paths = tuple(item.relative_path for item in bundle.documents)
    canonical_paths = tuple(_canonical_relative_path(item) for item in paths)
    if paths != canonical_paths or len(paths) != len(set(paths)):
        raise ValueError("canonical Java bundle path set is not canonical and unique")
    if len({item.casefold() for item in paths}) != len(paths):
        raise ValueError("canonical Java bundle has a casefold path collision")
    expected_order = tuple(
        sorted(
            bundle.documents,
            key=lambda item: (item.relative_path.encode("utf-8"), item.bytes_hash),
        )
    )
    if bundle.documents != expected_order:
        raise ValueError("canonical Java bundle document order mismatch")
    expected_tags = tuple(sorted(set(bundle.domain_tags)))
    if bundle.domain_tags != expected_tags:
        raise ValueError("canonical Java bundle domain tags are not sorted and unique")
    for document in bundle.documents:
        identity_body = {
            "schema_version": bundle.manifest.schema_version,
            "bundle_id": bundle.bundle_id,
            "relative_path": document.relative_path,
            "bytes_hash": document.bytes_hash,
        }
        expected_id = f"{bundle.bundle_id}.document.{content_hash(identity_body)[:32]}"
        if document.document_id != expected_id:
            raise ValueError("canonical Java document ID is not content-derived")
        if document.source_metadata != (("original_name", document.relative_path),):
            raise ValueError("canonical Java document metadata leaks a source root")


def _document_semantic_body(values) -> dict:
    """Exclude the acquisition event timestamp from semantic identity."""

    return {key: value for key, value in values.items() if key != "imported_at"}


def _bundle_semantic_body(values) -> dict:
    """Bind stable document identities, not platform/audit event metadata."""

    documents = values["documents"]
    return {
        "schema_version": values["manifest"].schema_version
        if hasattr(values["manifest"], "schema_version")
        else values["manifest"]["schema_version"],
        "bundle_id": values["bundle_id"],
        "domain_tags": values["domain_tags"],
        "document_hashes": tuple(
            item.document_hash
            if hasattr(item, "document_hash")
            else item["document_hash"]
            for item in documents
        ),
        "manifest_hash": values["manifest"].manifest_hash
        if hasattr(values["manifest"], "manifest_hash")
        else values["manifest"]["manifest_hash"],
    }


def _canonical_relative_path(value: str, *, require_nfc: bool = True) -> str:
    if not value or "\\" in value or "\x00" in value or re.match(r"^[A-Za-z]:", value):
        raise ValueError("non-canonical source relative path")
    normalized = unicodedata.normalize("NFC", value)
    if require_nfc and normalized != value:
        raise ValueError("source relative path is not NFC")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe source relative path")
    if normalized != path.as_posix():
        raise ValueError("source relative path is not canonical POSIX")
    return normalized


def _media_type(path: Path, raw: bytes) -> SourceMediaType:
    try:
        media = _EXTENSIONS[path.suffix.casefold()]
    except KeyError as error:
        raise ValueError("unsupported bounded source format") from error
    if media is SourceMediaType.PDF and not raw.startswith(b"%PDF-"):
        raise ValueError("malformed PDF source")
    if media is SourceMediaType.HTML and b"javadoc" in raw[:4096].lower():
        return SourceMediaType.JAVADOC_HTML
    return media


def _canonical_text(raw: bytes, media: SourceMediaType) -> str:
    if media is SourceMediaType.PDF:
        return _pdf_text(raw)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("source is not strict UTF-8") from error
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if media in {SourceMediaType.HTML, SourceMediaType.JAVADOC_HTML}:
        parser = _StaticHTML()
        parser.feed(text)
        parser.close()
        text = "\n".join(item.strip() for item in parser.text if item.strip())
    elif media is SourceMediaType.JSON:
        value = json.loads(text, object_pairs_hook=_strict_object)
        _bounded_nesting(value)
        text = canonical_json(value)
    return text.rstrip() + "\n"


def _pdf_text(raw: bytes) -> str:
    if b"/JavaScript" in raw or b"/JS" in raw or b"/EmbeddedFile" in raw:
        raise ValueError("active or embedded PDF content is forbidden")
    strings = re.findall(rb"\(([^()]*)\)\s*Tj", raw)
    if not strings:
        raise ValueError("PDF has no bounded text layer")
    try:
        return (
            "\n".join(
                item.decode("utf-8", errors="strict") for item in strings
            ).rstrip()
            + "\n"
        )
    except UnicodeDecodeError as error:
        raise ValueError("PDF text layer is not strict UTF-8") from error


class _StaticHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self._forbidden_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = {key.casefold(): (value or "") for key, value in attrs}
        if tag.casefold() in {"script", "style", "iframe", "object", "embed"}:
            raise ValueError("active HTML content is forbidden")
        style = attributes.get("style", "").replace(" ", "").casefold()
        if (
            "display:none" in style
            or "visibility:hidden" in style
            or "hidden" in attributes
        ):
            raise ValueError("hidden HTML content is forbidden")
        for key in ("href", "src"):
            if re.match(
                r"^(?:https?:|file:|javascript:|//)",
                attributes.get(key, ""),
                re.IGNORECASE,
            ):
                raise ValueError("external or active HTML reference is forbidden")
        if tag.casefold() in {
            "p",
            "div",
            "section",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "pre",
            "code",
        }:
            self.text.append("\n")

    def handle_data(self, data):
        self.text.append(data)


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in source")
        result[key] = value
    return result


def _bounded_nesting(value, depth=0):
    if depth > MAX_JSON_NESTING:
        raise ValueError("JSON nesting exceeds resource policy")
    if isinstance(value, dict):
        for child in value.values():
            _bounded_nesting(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _bounded_nesting(child, depth + 1)


def _structure(text: str, media: SourceMediaType) -> DocumentStructure:
    lines = text.splitlines()
    body = {
        "heading_count": sum(line.lstrip().startswith("#") for line in lines),
        "table_count": sum(line.count("|") >= 2 for line in lines),
        "code_block_count": sum(line.lstrip().startswith("```") for line in lines) // 2,
        "page_count": 1 if media is SourceMediaType.PDF else None,
    }
    return DocumentStructure(**body, structure_hash=content_hash(body))
