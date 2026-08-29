"""Bounded offline source ingestion. No fetch, script, OCR, macro or archive path."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path

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
    store=None,
) -> SourceBundle:
    if not bundle_id or not paths or len(paths) > MAX_DOCUMENTS:
        raise ValueError("source bundle identity or document count is invalid")
    if language not in {"ru", "en", "mixed"}:
        raise ValueError("unsupported source language")
    stamp = imported_at or utc_now()
    normalize_datetime(stamp)
    resolved = tuple(path.resolve(strict=True) for path in paths)
    if len(set(resolved)) != len(resolved):
        raise ValueError("duplicate source document")
    total = sum(path.stat().st_size for path in resolved)
    if total > MAX_BUNDLE_BYTES:
        raise ValueError("source bundle exceeds resource policy")
    documents = []
    for index, path in enumerate(resolved):
        if paths[index].is_symlink() or not path.is_file():
            raise ValueError("source symlink or non-file is forbidden")
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise ValueError("source document size is outside policy")
        media = _media_type(path, raw)
        canonical = _canonical_text(raw, media)
        if any(
            len(line.encode("utf-8")) > MAX_LINE_BYTES
            for line in canonical.splitlines()
        ):
            raise ValueError("source line exceeds resource policy")
        raw_hash = bytes_hash(raw)
        text_hash = bytes_hash(canonical.encode("utf-8"))
        document_id = f"{bundle_id}.document.{index + 1:03d}"
        structure = _structure(canonical, media)
        values = {
            "document_id": document_id,
            "media_type": media,
            "language": language,
            "relative_path": path.name,
            "bytes_hash": raw_hash,
            "canonical_text_hash": text_hash,
            "source_metadata": (("original_name", path.name),),
            "imported_at": stamp,
            "version": version,
            "parent_bundle_id": bundle_id,
            "structure": structure,
        }
        document = SourceDocument(**values, document_hash=content_hash(values))
        documents.append(document)
        if store is not None:
            store.put_blob(raw, expected_hash=raw_hash)
            store.put_blob(canonical.encode("utf-8"), expected_hash=text_hash)
    manifest_values = {
        "compiler_version": SOURCE_COMPILER_VERSION,
        "resource_policy_hash": content_hash(_RESOURCE_POLICY),
        "runtime_network": False,
        "document_hashes": tuple(item.document_hash for item in documents),
        "schema_version": ACQUISITION_SCHEMA_VERSION,
    }
    manifest = AcquisitionManifest(
        **manifest_values, manifest_hash=content_hash(manifest_values)
    )
    bundle_values = {
        "bundle_id": bundle_id,
        "domain_tags": tuple(dict.fromkeys(domain_tags)),
        "documents": tuple(documents),
        "manifest": manifest,
        "created_at": stamp,
    }
    bundle = SourceBundle(**bundle_values, bundle_hash=content_hash(bundle_values))
    verify_bundle(bundle, store=store)
    if store is not None:
        store.save_bundle(bundle)
    return bundle


def verify_bundle(bundle: SourceBundle, *, store=None) -> None:
    if (
        bundle.manifest.compiler_version != SOURCE_COMPILER_VERSION
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
    for document in bundle.documents:
        body = asdict(document)
        digest = body.pop("document_hash")
        if (
            document.parent_bundle_id != bundle.bundle_id
            or content_hash(body) != digest
        ):
            raise ValueError("source document hash or parent mismatch")
        if store is not None:
            raw = store.get_blob(document.bytes_hash)
            canonical = store.get_blob(document.canonical_text_hash)
            if (
                bytes_hash(raw) != document.bytes_hash
                or bytes_hash(canonical) != document.canonical_text_hash
            ):
                raise ValueError("stored source bytes changed")
    body = asdict(bundle)
    digest = body.pop("bundle_hash")
    if content_hash(body) != digest:
        raise ValueError("source bundle hash mismatch")


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
