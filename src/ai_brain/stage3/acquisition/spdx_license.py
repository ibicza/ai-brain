"""Deterministic SPDX-template license identification over a frozen snapshot."""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

SPDX_SNAPSHOT_VERSION = "3.28.0"
SPDX_SNAPSHOT_ROOT = Path(__file__).with_name("data") / "spdx" / SPDX_SNAPSHOT_VERSION
SPDX_MATCHER_VERSION = "spdx-template-matcher.v1"
SUPPORTED_LICENSE_IDS = (
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "GPL-2.0-only",
    "Classpath-exception-2.0",
)
_XML_NAMESPACE = "{http://www.spdx.org/license}"
_LICENSE_NAMES = frozenset(
    {
        "license",
        "license.txt",
        "license.md",
        "licence",
        "licence.txt",
        "licence.md",
        "copying",
        "copying.txt",
        "copying.md",
    }
)
_NOTICE_NAMES = frozenset({"notice", "notice.txt", "notice.md", "notices.txt"})
_DEPENDENCY_MARKERS = ("dependenc", "third-party", "third_party", "thirdparty")


class LicenseDocumentRole(StrEnum):
    PROJECT_LICENSE = "PROJECT_LICENSE"
    MODULE_LICENSE = "MODULE_LICENSE"
    NOTICE = "NOTICE"
    THIRD_PARTY_LICENSE = "THIRD_PARTY_LICENSE"
    DEPENDENCY_LICENSE = "DEPENDENCY_LICENSE"
    COPYRIGHT_NOTICE = "COPYRIGHT_NOTICE"
    UNKNOWN_LICENSE_DOCUMENT = "UNKNOWN_LICENSE_DOCUMENT"


class LicenseConflictClassification(StrEnum):
    BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT = "BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT"
    OPTIONAL_APPENDIX_OMITTED = "OPTIONAL_APPENDIX_OMITTED"
    OPTIONAL_HEADING_OMITTED = "OPTIONAL_HEADING_OMITTED"
    REPLACEABLE_TEXT_DIFFERENCE = "REPLACEABLE_TEXT_DIFFERENCE"
    FORMATTING_ONLY = "FORMATTING_ONLY"
    WRONG_LICENSE_DOCUMENT_SELECTED = "WRONG_LICENSE_DOCUMENT_SELECTED"
    TRUE_INCOMPATIBLE_LICENSE = "TRUE_INCOMPATIBLE_LICENSE"
    ADDITIONAL_TERMS = "ADDITIONAL_TERMS"
    UNRECOGNIZED_REVIEW_REQUIRED = "UNRECOGNIZED_REVIEW_REQUIRED"


class SPDXLicenseMatchStatus(StrEnum):
    EXACT_BYTES_MATCH = "EXACT_BYTES_MATCH"
    EXACT_NORMALIZED_MATCH = "EXACT_NORMALIZED_MATCH"
    SPDX_TEMPLATE_MATCH = "SPDX_TEMPLATE_MATCH"
    MULTIPLE_TEMPLATE_MATCH = "MULTIPLE_TEMPLATE_MATCH"
    NEAR_MATCH_REVIEW_REQUIRED = "NEAR_MATCH_REVIEW_REQUIRED"
    NO_MATCH = "NO_MATCH"
    MALFORMED = "MALFORMED"


AUTOMATIC_SPDX_MATCH_STATUSES = frozenset(
    {
        SPDXLicenseMatchStatus.EXACT_BYTES_MATCH,
        SPDXLicenseMatchStatus.EXACT_NORMALIZED_MATCH,
        SPDXLicenseMatchStatus.SPDX_TEMPLATE_MATCH,
    }
)


@dataclass(frozen=True)
class SPDXLicenseTemplate:
    license_id: str
    xml_path: str
    text_path: str
    xml_sha256: str
    text_sha256: str
    template_hash: str


@dataclass(frozen=True)
class SPDXLicenseMatchReceipt:
    source_document: str
    source_document_sha256: str
    document_role: LicenseDocumentRole
    spdx_snapshot_hash: str
    template_license_id: str | None
    matched_required_clauses: tuple[str, ...]
    accepted_optional_omissions: tuple[str, ...]
    accepted_replaceable_spans: tuple[str, ...]
    unmatched_substantive_spans: tuple[str, ...]
    matcher_implementation_hash: str
    match_status: SPDXLicenseMatchStatus
    receipt_hash: str


@dataclass(frozen=True)
class _CompiledTemplate:
    public: SPDXLicenseTemplate
    canonical: bytes
    normalized_canonical: bytes
    pattern: re.Pattern[str]
    required_clauses: tuple[str, ...]
    optional_sections: tuple[tuple[str, str], ...]
    replaceable_spans: tuple[tuple[str, str], ...]


def classify_license_document(path: str) -> LicenseDocumentRole:
    """Classify a license-like path without treating notices as project licenses."""

    normalized = unicodedata.normalize("NFC", path.replace("\\", "/")).strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("license document path is not canonical")
    parts = tuple(PurePosixPath(normalized).parts)
    name = parts[-1].casefold()
    lowered = normalized.casefold()
    if name in _NOTICE_NAMES or name.startswith(("notice-", "notice.")):
        return LicenseDocumentRole.NOTICE
    if name.startswith("copyright"):
        return LicenseDocumentRole.COPYRIGHT_NOTICE
    if "licenseslashstarstyle" in name or "licenseheader" in name:
        return LicenseDocumentRole.COPYRIGHT_NOTICE
    if "dependenc" in name:
        return LicenseDocumentRole.DEPENDENCY_LICENSE
    if any(marker in lowered for marker in _DEPENDENCY_MARKERS):
        return LicenseDocumentRole.THIRD_PARTY_LICENSE
    is_license_name = name in _LICENSE_NAMES or name.startswith(
        ("license-", "license.", "licence-", "licence.", "copying-", "copying.")
    )
    if not is_license_name:
        return LicenseDocumentRole.UNKNOWN_LICENSE_DOCUMENT
    if any(
        part.casefold()
        in {
            "docs",
            "doc",
            "assets",
            "vendor",
            "vendors",
            "legal",
            "licenses",
            "third-party",
            "third_party",
            "dependencies",
        }
        for part in parts[:-1]
    ):
        return LicenseDocumentRole.THIRD_PARTY_LICENSE
    # SCM archives have one synthetic top directory. JAR META-INF is a root channel.
    effective = parts[1:] if parts and re.search(r"-[0-9a-f]{40}$", parts[0]) else parts
    if len(effective) == 1 or (
        len(effective) == 2 and effective[0].casefold() == "meta-inf"
    ):
        return LicenseDocumentRole.PROJECT_LICENSE
    return LicenseDocumentRole.MODULE_LICENSE


class SPDXLicenseMatcher:
    """Load verified XML templates and perform only exact or template matches."""

    def __init__(self, snapshot_root: Path = SPDX_SNAPSHOT_ROOT):
        self.snapshot_root = snapshot_root.resolve(strict=True)
        self.snapshot = self._load_snapshot()
        self.snapshot_hash = self.snapshot["snapshot_manifest_hash"]
        self.templates = tuple(
            self._load_template(item) for item in SUPPORTED_LICENSE_IDS
        )
        self.implementation_hash = bytes_hash(Path(__file__).read_bytes())
        self._template_match_cache: dict[str, tuple[_CompiledTemplate, ...]] = {}

    def match(
        self,
        raw: bytes,
        *,
        source_document: str,
        document_role: LicenseDocumentRole | None = None,
    ) -> SPDXLicenseMatchReceipt:
        role = document_role or classify_license_document(source_document)
        try:
            decoded = raw.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            return self._receipt(
                raw,
                source_document,
                role,
                None,
                SPDXLicenseMatchStatus.MALFORMED,
            )
        exact = tuple(item for item in self.templates if raw == item.canonical)
        if len(exact) == 1:
            return self._receipt(
                raw,
                source_document,
                role,
                exact[0],
                SPDXLicenseMatchStatus.EXACT_BYTES_MATCH,
            )
        normalized = normalize_spdx_text(decoded).encode("utf-8")
        normalized_matches = tuple(
            item for item in self.templates if normalized == item.normalized_canonical
        )
        if len(normalized_matches) == 1:
            return self._receipt(
                raw,
                source_document,
                role,
                normalized_matches[0],
                SPDXLicenseMatchStatus.EXACT_NORMALIZED_MATCH,
            )
        lexical = _lexical_text(decoded)
        template_matches = self._template_match_cache.get(lexical)
        if template_matches is None:
            template_matches = tuple(
                item
                for item in self.templates
                if _required_prefilter(item.public.license_id, lexical)
                and _matches_template(item, lexical)
            )
            self._template_match_cache[lexical] = template_matches
        if len(template_matches) == 1:
            return self._receipt(
                raw,
                source_document,
                role,
                template_matches[0],
                SPDXLicenseMatchStatus.SPDX_TEMPLATE_MATCH,
                lexical=lexical,
            )
        if len(template_matches) > 1:
            return self._receipt(
                raw,
                source_document,
                role,
                None,
                SPDXLicenseMatchStatus.MULTIPLE_TEMPLATE_MATCH,
                unmatched=("multiple-frozen-templates",),
            )
        additional_terms = tuple(
            item
            for item in self.templates
            if _required_prefilter(item.public.license_id, lexical)
            and _has_additional_terms(item, lexical)
        )
        if len(additional_terms) == 1:
            return self._receipt(
                raw,
                source_document,
                role,
                additional_terms[0],
                SPDXLicenseMatchStatus.NEAR_MATCH_REVIEW_REQUIRED,
                unmatched=("additional-substantive-terms",),
            )
        markers = {
            "apache-2.0": ("apache license", "grant of patent license"),
            "mit": ("permission is hereby granted", "the software is provided"),
            "bsd-2-clause": ("redistribution and use", "disclaimer"),
            "bsd-3-clause": ("redistribution and use", "neither the name"),
            "gpl-2.0-only": ("gnu general public license", "version 2"),
        }
        near = tuple(
            license_id
            for license_id, phrases in markers.items()
            if all(_lexical_text(phrase) in lexical for phrase in phrases)
        )
        status = (
            SPDXLicenseMatchStatus.NEAR_MATCH_REVIEW_REQUIRED
            if near
            else SPDXLicenseMatchStatus.NO_MATCH
        )
        return self._receipt(
            raw,
            source_document,
            role,
            None,
            status,
            unmatched=(f"sha256:{bytes_hash(normalized)}", f"bytes:{len(raw)}"),
        )

    def _load_snapshot(self) -> dict:
        path = self.snapshot_root / "snapshot.json"
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
        expected = {
            "schema_version",
            "license_list_version",
            "license_xml_repository",
            "license_xml_tag",
            "license_xml_tag_object",
            "license_xml_commit",
            "license_data_repository",
            "license_data_tag",
            "license_data_tag_object",
            "license_data_commit",
            "specification_repository",
            "specification_tag",
            "specification_tag_object",
            "specification_commit",
            "files",
            "snapshot_manifest_hash",
        }
        if (
            set(value) != expected
            or value["license_list_version"] != SPDX_SNAPSHOT_VERSION
        ):
            raise ValueError("SPDX snapshot manifest schema/version mismatch")
        body = dict(value)
        claimed = body.pop("snapshot_manifest_hash")
        if content_hash(body) != claimed:
            raise ValueError("SPDX snapshot manifest hash mismatch")
        for relative, digest in value["files"]:
            target = (self.snapshot_root / relative).resolve(strict=True)
            if (
                not target.is_relative_to(self.snapshot_root)
                or bytes_hash(target.read_bytes()) != digest
            ):
                raise ValueError("SPDX snapshot file hash mismatch")
        return value

    def _load_template(self, license_id: str) -> _CompiledTemplate:
        xml_path = self.snapshot_root / f"{license_id}.xml"
        text_path = self.snapshot_root / f"{license_id}.txt"
        xml_raw = xml_path.read_bytes()
        canonical = text_path.read_bytes()
        root = ET.fromstring(xml_raw)
        license_node = root.find(f"{_XML_NAMESPACE}license")
        if license_node is None:
            license_node = root.find(f"{_XML_NAMESPACE}exception")
        if license_node is None or license_node.attrib.get("licenseId") != license_id:
            raise ValueError("SPDX XML license identity mismatch")
        text_node = license_node.find(f"{_XML_NAMESPACE}text")
        if text_node is None:
            raise ValueError("SPDX XML template has no text")
        optional: list[tuple[str, str]] = []
        replaceable: list[tuple[str, str]] = []
        expression = _compile_xml(text_node, optional, replaceable)
        required = _required_clause_names(license_id, text_node)
        public_body = {
            "license_id": license_id,
            "xml_path": xml_path.name,
            "text_path": text_path.name,
            "xml_sha256": bytes_hash(xml_raw),
            "text_sha256": bytes_hash(canonical),
        }
        public = SPDXLicenseTemplate(
            **public_body, template_hash=content_hash(public_body)
        )
        return _CompiledTemplate(
            public=public,
            canonical=canonical,
            normalized_canonical=normalize_spdx_bytes(canonical),
            pattern=re.compile(r"\A\s*" + expression + r"\s*\Z"),
            required_clauses=required,
            optional_sections=tuple(optional),
            replaceable_spans=tuple(replaceable),
        )

    def _receipt(
        self,
        raw,
        source_document,
        role,
        template,
        status,
        *,
        lexical="",
        unmatched=(),
    ):
        accepted = status in AUTOMATIC_SPDX_MATCH_STATUSES
        optional_omissions = ()
        replaceable_spans = ()
        if accepted and template is not None:
            optional_omissions = tuple(
                name
                for name, canonical in template.optional_sections
                if canonical and not _optional_present(name, canonical, lexical)
            )
            replaceable_spans = tuple(
                name
                for name, canonical in template.replaceable_spans
                if canonical and canonical not in lexical
            )
        body = {
            "source_document": source_document,
            "source_document_sha256": bytes_hash(raw),
            "document_role": role,
            "spdx_snapshot_hash": self.snapshot_hash,
            "template_license_id": template.public.license_id if template else None,
            "matched_required_clauses": template.required_clauses
            if accepted and template
            else (),
            "accepted_optional_omissions": optional_omissions,
            "accepted_replaceable_spans": replaceable_spans,
            "unmatched_substantive_spans": tuple(unmatched),
            "matcher_implementation_hash": self.implementation_hash,
            "match_status": status,
        }
        return SPDXLicenseMatchReceipt(**body, receipt_hash=content_hash(body))


def normalize_spdx_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip() + "\n"


def normalize_spdx_bytes(raw: bytes) -> bytes:
    return normalize_spdx_text(raw.decode("utf-8-sig", errors="strict")).encode("utf-8")


def first_differing_span(left: bytes, right: bytes) -> dict[str, object]:
    """Return the exact first non-equal normalized span without fuzzy authority."""

    left_text = normalize_spdx_bytes(left).decode("utf-8")
    right_text = normalize_spdx_bytes(right).decode("utf-8")
    matcher = difflib.SequenceMatcher(a=left_text, b=right_text, autojunk=False)
    opcode = next((item for item in matcher.get_opcodes() if item[0] != "equal"), None)
    if opcode is None:
        return {
            "kind": "EQUAL",
            "left": "",
            "right": "",
            "left_offset": len(left_text),
            "right_offset": len(right_text),
        }
    kind, left_start, left_end, right_start, right_end = opcode
    return {
        "kind": kind.upper(),
        "left": left_text[left_start:left_end],
        "right": right_text[right_start:right_end],
        "left_offset": left_start,
        "right_offset": right_start,
    }


def classify_license_difference(
    receipt: SPDXLicenseMatchReceipt,
    *,
    compared_as_project_license: bool = True,
) -> LicenseConflictClassification:
    if not compared_as_project_license:
        return LicenseConflictClassification.WRONG_LICENSE_DOCUMENT_SELECTED
    if receipt.match_status is SPDXLicenseMatchStatus.EXACT_NORMALIZED_MATCH:
        return LicenseConflictClassification.FORMATTING_ONLY
    if receipt.match_status is SPDXLicenseMatchStatus.SPDX_TEMPLATE_MATCH:
        if "optional-appendix" in receipt.accepted_optional_omissions:
            return LicenseConflictClassification.OPTIONAL_APPENDIX_OMITTED
        if receipt.accepted_optional_omissions:
            return LicenseConflictClassification.OPTIONAL_HEADING_OMITTED
        if receipt.accepted_replaceable_spans:
            return LicenseConflictClassification.REPLACEABLE_TEXT_DIFFERENCE
        return LicenseConflictClassification.BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT
    if receipt.template_license_id and receipt.template_license_id != "Apache-2.0":
        return LicenseConflictClassification.TRUE_INCOMPATIBLE_LICENSE
    if "additional-substantive-terms" in receipt.unmatched_substantive_spans:
        return LicenseConflictClassification.ADDITIONAL_TERMS
    if receipt.match_status is SPDXLicenseMatchStatus.NEAR_MATCH_REVIEW_REQUIRED:
        return LicenseConflictClassification.UNRECOGNIZED_REVIEW_REQUIRED
    return LicenseConflictClassification.UNRECOGNIZED_REVIEW_REQUIRED


def _compile_xml(node, optional, replaceable) -> str:
    pieces = [_literal(node.text or "")]
    for child in node:
        tag = child.tag.removeprefix(_XML_NAMESPACE)
        rendered = _compile_xml(child, optional, replaceable)
        canonical = _lexical_text("".join(child.itertext()))
        if tag == "optional":
            name = _optional_name(canonical, len(optional))
            optional.append((name, canonical))
            pieces.append(f"(?:{rendered})?")
        elif tag == "alt":
            name = child.attrib.get("name", f"replaceable-{len(replaceable)}")
            replaceable.append((name, canonical))
            pieces.append(r"(?:\S+(?:\s+\S+){0,64})")
        elif tag == "copyrightText":
            replaceable.append(("copyright-text", canonical))
            pieces.append(r"(?:\S+(?:\s+\S+){0,64}\s+)?")
        elif tag == "bullet":
            pieces.append(r"(?:[a-z0-9]{1,4}\s+)?")
        elif tag == "br":
            pieces.append(r"\s+")
        else:
            pieces.append(rendered)
        pieces.append(_literal(child.tail or ""))
    return "".join(pieces)


def _literal(value: str) -> str:
    normalized = _lexical_text(value)
    if not normalized:
        return r"\s*"
    return r"\s+".join(re.escape(item) for item in normalized.split()) + r"\s*"


def _lexical_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).casefold()
    value = re.sub(r"https?://", "http://", value)
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _optional_name(value: str, index: int) -> str:
    if "appendix how to apply the apache license" in value:
        return "optional-appendix"
    if "terms and conditions for use reproduction and distribution" in value:
        return "optional-heading"
    if "end of terms and conditions" in value:
        return "optional-end-heading"
    return f"optional-{index}"


def _optional_present(name: str, canonical: str, lexical: str) -> bool:
    markers = {
        "optional-appendix": "appendix how to apply the apache license",
        "optional-heading": "terms and conditions for use reproduction and distribution",
        "optional-end-heading": "end of terms and conditions",
    }
    marker = markers.get(name, canonical)
    return marker in lexical


def _required_clause_names(license_id: str, text_node) -> tuple[str, ...]:
    if license_id == "Apache-2.0":
        return (
            "definitions",
            "copyright-grant",
            "patent-grant",
            "redistribution",
            "submission-of-contributions",
            "trademarks",
            "warranty-disclaimer",
            "liability-limitation",
            "additional-liability",
        )
    required = tuple(
        _lexical_text("".join(item.itertext()))[:80]
        for item in text_node
        if item.tag.removeprefix(_XML_NAMESPACE) != "optional"
        and _lexical_text("".join(item.itertext()))
    )
    return required or (license_id.casefold(),)


def _required_prefilter(license_id: str, lexical: str) -> bool:
    """Cheap rejection only; a successful prefilter never grants authority."""

    anchors = {
        "Apache-2.0": (
            "apache license",
            "grant of patent license",
            "patent license to make",
            "redistribution",
            "you must give any other recipients",
            "royalty free",
            "irrevocable",
            "limitation of liability",
            "without warranties or conditions of any kind",
        ),
        "MIT": ("permission is hereby granted", "the software is provided as is"),
        "BSD-2-Clause": ("redistribution and use", "this software is provided"),
        "BSD-3-Clause": (
            "redistribution and use",
            "neither the name",
            "this software is provided",
        ),
        "GPL-2.0-only": (
            "gnu general public license",
            "version 2 june 1991",
            "no warranty",
        ),
        "Classpath-exception-2.0": (
            "linking this library",
            "as a special exception",
            "independent module",
        ),
    }[license_id]
    return all(anchor in lexical for anchor in anchors)


def _matches_template(template: _CompiledTemplate, lexical: str) -> bool:
    if template.public.license_id != "Apache-2.0":
        return template.pattern.fullmatch(lexical) is not None
    bases = _apache_template_bases(template)
    if lexical in bases:
        return True
    placeholder = "yyyy name of copyright owner"
    for base in bases:
        if placeholder not in base:
            continue
        prefix, suffix = base.split(placeholder, 1)
        if lexical.startswith(prefix) and lexical.endswith(suffix):
            middle = lexical[len(prefix) : len(lexical) - len(suffix)]
            if 1 <= len(middle.split()) <= 64:
                return True
    return False


def _apache_template_bases(template: _CompiledTemplate) -> set[str]:
    canonical = _lexical_text(template.canonical.decode("utf-8"))
    headings = (
        "terms and conditions for use reproduction and distribution ",
        "end of terms and conditions ",
    )
    appendix = "appendix how to apply the apache license to your work "
    bases = {canonical}
    for heading in headings:
        bases |= {item.replace(heading, "", 1) for item in tuple(bases)}
    bases |= {
        item[: item.index(appendix)].strip()
        for item in tuple(bases)
        if appendix in item
    }
    return bases


def _has_additional_terms(template: _CompiledTemplate, lexical: str) -> bool:
    if template.public.license_id != "Apache-2.0":
        canonical = _lexical_text(template.canonical.decode("utf-8"))
        return lexical.startswith(canonical) and lexical != canonical
    return any(
        lexical.startswith(base + " ") for base in _apache_template_bases(template)
    )


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate SPDX snapshot JSON key")
        result[key] = value
    return result


def dump_spdx_match_receipt(receipt: SPDXLicenseMatchReceipt) -> dict:
    return asdict(receipt)
