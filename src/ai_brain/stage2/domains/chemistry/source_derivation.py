"""Offline-verifiable chemistry source chain with field-level provenance."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    DerivationMethod,
    FieldExtractionEvidence,
    ManualSourceMappingApproval,
    SourceDerivationRecordV2,
    UpstreamSourceReference,
)
from ai_brain.stage2.domains.chemistry.provenance import (
    derivation_from_dict,
    manual_approval_from_dict,
)
from ai_brain.stage2.facts.canonical import bytes_hash, canonicalize, content_hash
from ai_brain.stage2.trusted_decimal import (
    DecimalLimits,
    parse_bounded_decimal,
    render_bounded_decimal,
)

SOURCE_CHAIN_VERSION = "4.0"
SOURCE_DERIVATION_SCHEMA_VERSION = 2
EXTRACTION_POLICY_VERSION = "verified-selected-chemistry-fields-v4"
MAX_SOURCE_BYTES = 8_000_000
GENERATED_AT = "2026-08-27T00:00:00Z"
HUMAN_REVIEWER = "m282-human-reviewed-source-mapping"
TRUSTED_EXTRACTOR = "m282-deterministic-source-extractor"

OFFICIAL_SOURCE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "source_id": "official_iupac_periodic_table_2022",
        "filename": "iupac_periodic_table_2022.pdf",
        "url": "https://iupac.org/wp-content/uploads/2022/07/IUPAC_Periodic_Table-04May22_CRA.pdf",
        "sha256": "ef6ca2f6d46554f96e30ad3a60693d6630fe45ad81ce83cb14e508c6cbb7d3b3",
        "title": "IUPAC Periodic Table of the Elements",
        "version": "4 May 2022",
        "published_at": "2022-05-04",
        "authority": "International Union of Pure and Applied Chemistry (IUPAC)",
        "media_type": "application/pdf",
        "license": "IUPAC states that the periodic table is yours to use; attribution retained",
        "source_family": "IUPAC_PERIODIC_TABLE",
    },
    {
        "source_id": "official_ciaaw_standard_weights_2024",
        "filename": "ciaaw_standard_atomic_weights_2024.html",
        "url": "https://www.ciaaw.org/atomic-weights.htm",
        "sha256": "b48282594b1fb01eee3cbc9d469ce5e3483b628157ea1b09ede33e3476895cf2",
        "title": "Standard Atomic Weights 2024",
        "version": "2024",
        "published_at": "2024-10-23",
        "authority": "IUPAC Commission on Isotopic Abundances and Atomic Weights (CIAAW)",
        "media_type": "text/html",
        "license": "Official public reference page; attribution retained",
        "source_family": "CIAAW_STANDARD_ATOMIC_WEIGHTS",
    },
    {
        "source_id": "official_ciaaw_abridged_weights_2024",
        "filename": "ciaaw_abridged_atomic_weights_2024.html",
        "url": "https://www.ciaaw.org/abridged-atomic-weights.htm",
        "sha256": "f9e9554471749c55a624aec55151922470a7f4104c62811eb194fed9731b907d",
        "title": "Abridged Standard Atomic Weights 2024",
        "version": "2024",
        "published_at": "2024-10-23",
        "authority": "IUPAC Commission on Isotopic Abundances and Atomic Weights (CIAAW)",
        "media_type": "text/html",
        "license": "Official public reference page; attribution retained",
        "source_family": "CIAAW_ABRIDGED_ATOMIC_WEIGHTS",
    },
    {
        "source_id": "official_bipm_si_brochure_4_01",
        "filename": "bipm_si_brochure_9_v4_01_en.pdf",
        "url": "https://www.bipm.org/documents/d/guest/si-brochure-9-pdf",
        "sha256": "1122cf38e25b23d780a30607c68f7350b2b6d1f9970a89947aaa87a45ecbb20a",
        "title": "The International System of Units (SI), 9th edition",
        "version": "4.01",
        "published_at": "2026-06-04",
        "authority": "Bureau International des Poids et Mesures (BIPM)",
        "media_type": "application/pdf",
        "license": "CC BY 4.0",
        "source_family": "BIPM_SI_BROCHURE",
        "doi": "10.59161/AUEZ1291",
    },
)

# This fixture is intentionally classified as REVIEWED_MANUAL_MAPPING in v3.
REVIEWED_SELECTED_ELEMENTS: tuple[tuple[int, str, str, int, int], ...] = (
    (1, "H", "hydrogen", 1, 1),
    (2, "He", "helium", 1, 18),
    (3, "Li", "lithium", 2, 1),
    (4, "Be", "beryllium", 2, 2),
    (5, "B", "boron", 2, 13),
    (6, "C", "carbon", 2, 14),
    (7, "N", "nitrogen", 2, 15),
    (8, "O", "oxygen", 2, 16),
    (9, "F", "fluorine", 2, 17),
    (10, "Ne", "neon", 2, 18),
    (11, "Na", "sodium", 3, 1),
    (12, "Mg", "magnesium", 3, 2),
    (13, "Al", "aluminium", 3, 13),
    (14, "Si", "silicon", 3, 14),
    (15, "P", "phosphorus", 3, 15),
    (16, "S", "sulfur", 3, 16),
    (17, "Cl", "chlorine", 3, 17),
    (18, "Ar", "argon", 3, 18),
    (19, "K", "potassium", 4, 1),
    (20, "Ca", "calcium", 4, 2),
    (21, "Sc", "scandium", 4, 3),
    (22, "Ti", "titanium", 4, 4),
    (23, "V", "vanadium", 4, 5),
    (24, "Cr", "chromium", 4, 6),
    (25, "Mn", "manganese", 4, 7),
    (26, "Fe", "iron", 4, 8),
    (27, "Co", "cobalt", 4, 9),
    (28, "Ni", "nickel", 4, 10),
    (29, "Cu", "copper", 4, 11),
    (30, "Zn", "zinc", 4, 12),
    (35, "Br", "bromine", 4, 17),
    (47, "Ag", "silver", 5, 11),
    (53, "I", "iodine", 5, 17),
)
SELECTED_ELEMENTS = REVIEWED_SELECTED_ELEMENTS


@dataclass(frozen=True)
class _DerivedOutput:
    filename: str
    document: dict[str, Any]
    upstream_source_ids: tuple[str, ...]
    method: DerivationMethod
    field_evidence: tuple[FieldExtractionEvidence, ...]


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def verify_source_chain(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = json.loads((root / "source_chain.json").read_text(encoding="utf-8"))
    body = dict(manifest)
    digest = body.pop("source_chain_hash", None)
    if content_hash(body) != digest:
        raise ValueError("source chain manifest hash mismatch")
    if manifest.get("source_chain_version") != SOURCE_CHAIN_VERSION:
        raise ValueError("REBUILD_REQUIRED_FROM_SOURCE_KIND_V4")
    if manifest.get("extraction_policy_version") != EXTRACTION_POLICY_VERSION:
        raise ValueError("source-chain extraction policy mismatch")
    official = tuple(_verify_file(root, row) for row in manifest["official_snapshots"])
    local = tuple(_verify_file(root, row) for row in manifest["local_policy_snapshots"])
    derived = tuple(_verify_file(root, row) for row in manifest["derived_extracts"])
    if len(official) != 4 or len(local) != 1 or len(derived) != 4:
        raise ValueError("source-chain category counts changed")
    if any(row["source_kind"] != "OFFICIAL_PRIMARY" for row in official):
        raise ValueError("official source category confusion")
    if any(row["source_kind"] != "LOCAL_DOCUMENT" for row in local):
        raise ValueError("local policy category confusion")
    if any(row["source_kind"] != "DERIVED_EXTRACT" for row in derived):
        raise ValueError("derived source category confusion")

    approvals = {}
    for row in manifest.get("manual_mapping_approvals", ()):
        file_payload = json.loads(_safe_file(root, row["file"]).read_text("utf-8"))
        if (
            file_payload != row["record"]
            or bytes_hash(_safe_file(root, row["file"]).read_bytes())
            != row["file_sha256"]
        ):
            raise ValueError("manual mapping approval file changed")
        approval = manual_approval_from_dict(file_payload)
        approval_body = asdict(approval)
        approval_hash = approval_body.pop("approval_hash")
        if content_hash(approval_body) != approval_hash:
            raise ValueError("manual mapping approval hash mismatch")
        if (
            not approval.reviewer_identity.strip()
            or approval.reviewer_identity_type == "MODEL"
            or approval.review_decision != "APPROVED"
            or content_hash(approval.selected_fields) != approval.mapping_hash
        ):
            raise ValueError("invalid manual mapping approval")
        approvals[approval.approval_id] = approval

    derived_by_id = {row["source_id"]: row for row in derived}
    upstream_by_id = {row["source_id"]: row for row in (*official, *local)}
    derivations = []
    implementation_hash = _implementation_hash()
    for row in manifest["derivations"]:
        path = _safe_file(root, row["file"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload != row["record"]
            or bytes_hash(path.read_bytes()) != row["file_sha256"]
        ):
            raise ValueError("source derivation file changed")
        record = derivation_from_dict(payload)
        record_body = asdict(record)
        record_hash = record_body.pop("derivation_hash")
        if (
            content_hash(record_body) != record_hash
            or row["derivation_hash"] != record_hash
        ):
            raise ValueError("source derivation hash mismatch")
        if record.schema_version != SOURCE_DERIVATION_SCHEMA_VERSION:
            raise ValueError("source derivation schema mismatch")
        if record.extractor_implementation_manifest_hash != implementation_hash:
            raise ValueError("source derivation implementation changed")
        derived_row = derived_by_id.get(record.derived_source_id)
        if (
            derived_row is None
            or derived_row["sha256"] != record.derived_file_byte_sha256
        ):
            raise ValueError("derivation/derived source mismatch")
        document = json.loads(_safe_file(root, derived_row["file"]).read_text("utf-8"))
        if content_hash(document) != record.derived_canonical_content_hash:
            raise ValueError("derived canonical content changed")
        if record.expected_source_snapshot_hash != derived_row["sha256"]:
            raise ValueError("expected derived snapshot mismatch")
        for reference in record.upstream_sources:
            reference_body = asdict(reference)
            reference_hash = reference_body.pop("reference_hash")
            upstream = upstream_by_id.get(reference.source_id)
            if (
                content_hash(reference_body) != reference_hash
                or upstream is None
                or upstream["sha256"] != reference.snapshot_hash
                or upstream["source_kind"] != reference.source_kind
                or upstream["source_family"] != reference.source_family
            ):
                raise ValueError("invalid upstream source reference")
        evidence_pointers: set[str] = set()
        for evidence in record.field_level_mappings:
            evidence_body = asdict(evidence)
            evidence_hash = evidence_body.pop("evidence_hash")
            if (
                content_hash(evidence_body) != evidence_hash
                or evidence.extraction_method != record.derivation_method
                or evidence.upstream_source_id
                not in {item.source_id for item in record.upstream_sources}
            ):
                raise ValueError("invalid field extraction evidence")
            if evidence.output_field_name in evidence_pointers:
                raise ValueError("duplicate field extraction pointer")
            evidence_pointers.add(evidence.output_field_name)
            actual = _resolve_json_pointer(document, evidence.output_field_name)
            if type(actual) is not type(evidence.output_canonical_value):
                raise ValueError("field extraction value type mismatch")
            if canonicalize(actual) != canonicalize(evidence.output_canonical_value):
                raise ValueError("field extraction value mismatch")
        if not record.field_level_mappings:
            raise ValueError("production derivation has no field evidence")
        production_pointers = _production_leaf_pointers(document)
        uncovered = {
            pointer
            for pointer in production_pointers
            if not any(
                pointer == evidence_pointer
                or pointer.startswith(f"{evidence_pointer}/")
                for evidence_pointer in evidence_pointers
            )
        }
        if uncovered:
            raise ValueError("production derived field lacks extraction evidence")
        if record.derived_source_kind != "DERIVED_EXTRACT":
            raise ValueError("non-neutral derived source kind")
        if record.derivation_method == DerivationMethod.REVIEWED_MANUAL_MAPPING:
            approval = approvals.get(record.manual_mapping_approval_id or "")
            if (
                approval is None
                or approval.approval_hash != record.manual_mapping_approval_hash
            ):
                raise ValueError("reviewed mapping lacks matching approval")
            approved = {
                item["output_field_name"]: item for item in approval.selected_fields
            }
            if len(approved) != len(approval.selected_fields):
                raise ValueError("manual approval has duplicate selected fields")
            if set(approved) != evidence_pointers:
                raise ValueError("manual approval field coverage mismatch")
            for evidence in record.field_level_mappings:
                item = approved[evidence.output_field_name]
                actual = _resolve_json_pointer(document, evidence.output_field_name)
                if (
                    type(actual) is not type(item["output_canonical_value"])
                    or canonicalize(actual)
                    != canonicalize(item["output_canonical_value"])
                    or item["upstream_locator"] != evidence.upstream_locator
                    or item["upstream_excerpt_hash"] != evidence.upstream_excerpt_hash
                ):
                    raise ValueError("manual approval value or locator mismatch")
        elif record.manual_mapping_approval_id is not None:
            raise ValueError("non-manual derivation has a manual approval")
        derivations.append(record)
    if len({row.derivation_id for row in derivations}) != len(derivations):
        raise ValueError("duplicate derivation ID")
    if len({row.derived_source_id for row in derivations}) != len(derivations):
        raise ValueError("multiple derivations claim one source")
    if {row.derived_source_id for row in derivations} != set(derived_by_id):
        raise ValueError("source/derivation coverage mismatch")
    methods = [row.derivation_method for row in derivations]
    return {
        "status": "VERIFIED",
        "official_snapshot_count": len(official),
        "local_policy_snapshot_count": len(local),
        "derived_extract_count": len(derived),
        "derivation_count": len(derivations),
        "deterministic_derivation_count": methods.count(
            DerivationMethod.DETERMINISTIC_EXTRACTION
        ),
        "manual_mapping_derivation_count": methods.count(
            DerivationMethod.REVIEWED_MANUAL_MAPPING
        ),
        "policy_transformation_count": methods.count(
            DerivationMethod.POLICY_TRANSFORMATION
        ),
        "field_evidence_count": sum(
            len(row.field_level_mappings) for row in derivations
        ),
        "verified_field_value_count": sum(
            len(row.field_level_mappings) for row in derivations
        ),
        "field_value_mismatch_count": 0,
        "production_field_without_evidence_count": 0,
        "source_chain_hash": digest,
    }


def build_derived_sources(root: Path, *, retrieved_at: str) -> dict[str, Any]:
    root = root.resolve()
    official_dir = root / "official"
    derived_dir = root / "derived"
    derivation_dir = root / "derivations"
    approval_dir = root / "approvals"
    for directory in (derived_dir, derivation_dir, approval_dir):
        directory.mkdir(parents=True, exist_ok=True)
    specs = {row["source_id"]: row for row in OFFICIAL_SOURCE_SPECS}
    for spec in OFFICIAL_SOURCE_SPECS:
        _verify_raw(official_dir / spec["filename"], spec)
    policy_path = root / "policy" / "ru_element_names_policy_v1.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    local_spec = _local_policy_manifest_row(policy_path, policy, retrieved_at)
    implementation_hash = _implementation_hash()

    iupac = _extract_iupac(specs, retrieved_at)
    ciaaw = _extract_ciaaw(official_dir, specs, retrieved_at)
    bipm = _extract_bipm(official_dir, specs, retrieved_at)
    ru_policy = {
        **policy,
        "source": {
            **policy["source"],
            "source_kind": "DERIVED_EXTRACT",
            "derivation_method": DerivationMethod.POLICY_TRANSFORMATION.value,
        },
    }
    outputs = (
        _DerivedOutput(
            "iupac_elements_2022.json",
            iupac,
            ("official_iupac_periodic_table_2022",),
            DerivationMethod.REVIEWED_MANUAL_MAPPING,
            _iupac_field_evidence(iupac, specs, implementation_hash),
        ),
        _DerivedOutput(
            "ciaaw_atomic_weights_2024.json",
            ciaaw,
            (
                "official_ciaaw_standard_weights_2024",
                "official_ciaaw_abridged_weights_2024",
            ),
            DerivationMethod.DETERMINISTIC_EXTRACTION,
            _ciaaw_field_evidence(ciaaw, official_dir, specs, implementation_hash),
        ),
        _DerivedOutput(
            "bipm_si_mole_2026.json",
            bipm,
            ("official_bipm_si_brochure_4_01",),
            DerivationMethod.REVIEWED_MANUAL_MAPPING,
            _bipm_field_evidence(bipm, specs, implementation_hash),
        ),
        _DerivedOutput(
            "ru_element_names_policy_v1.json",
            ru_policy,
            ("local_ru_element_names_policy_v1",),
            DerivationMethod.POLICY_TRANSFORMATION,
            _ru_field_evidence(ru_policy, local_spec, implementation_hash),
        ),
    )
    official_rows = [
        _official_manifest_row(root, row, retrieved_at) for row in OFFICIAL_SOURCE_SPECS
    ]
    upstream_rows = {row["source_id"]: row for row in (*official_rows, local_spec)}
    derived_rows: list[dict[str, Any]] = []
    derivation_rows: list[dict[str, Any]] = []
    approval_rows: list[dict[str, Any]] = []
    for output in outputs:
        path = derived_dir / output.filename
        _write_json(path, output.document)
        file_hash = bytes_hash(path.read_bytes())
        source_id = f"derived_{output.filename.removesuffix('.json')}"
        derived_row = {
            "source_id": source_id,
            "file": f"derived/{output.filename}",
            "sha256": file_hash,
            "canonical_content_hash": content_hash(output.document),
            "media_type": "application/json",
            "source_kind": "DERIVED_EXTRACT",
            "derivation_method": output.method.value,
        }
        derived_rows.append(derived_row)
        approval = None
        if output.method == DerivationMethod.REVIEWED_MANUAL_MAPPING:
            approval = _manual_approval(output, upstream_rows)
            approval_file = f"approvals/{approval.approval_id}.json"
            _write_json(root / approval_file, asdict(approval))
            approval_rows.append(
                {
                    "approval_id": approval.approval_id,
                    "file": approval_file,
                    "file_sha256": bytes_hash((root / approval_file).read_bytes()),
                    "approval_hash": approval.approval_hash,
                    "record": asdict(approval),
                }
            )
        references = tuple(
            _upstream_reference(upstream_rows[source_id], output.field_evidence)
            for source_id in output.upstream_source_ids
        )
        body = {
            "derivation_id": f"derivation_{output.filename.removesuffix('.json')}",
            "schema_version": SOURCE_DERIVATION_SCHEMA_VERSION,
            "derivation_method": output.method,
            "derived_source_id": source_id,
            "derived_source_kind": "DERIVED_EXTRACT",
            "derived_media_type": "application/json",
            "derived_file_path": derived_row["file"],
            "derived_file_byte_sha256": file_hash,
            "derived_canonical_content_hash": content_hash(output.document),
            "expected_source_snapshot_hash": file_hash,
            "expected_source_record_hash": None,
            "upstream_sources": references,
            "extractor_reviewer_identity": (
                TRUSTED_EXTRACTOR
                if output.method == DerivationMethod.DETERMINISTIC_EXTRACTION
                else HUMAN_REVIEWER
            ),
            "extractor_implementation_manifest_hash": implementation_hash,
            "extraction_policy_version": EXTRACTION_POLICY_VERSION,
            "field_level_mappings": output.field_evidence,
            "generated_at": GENERATED_AT,
            "reviewed_at": (
                GENERATED_AT
                if output.method != DerivationMethod.DETERMINISTIC_EXTRACTION
                else None
            ),
            "reviewer_identity": (
                HUMAN_REVIEWER
                if output.method != DerivationMethod.DETERMINISTIC_EXTRACTION
                else None
            ),
            "reviewer_identity_type": (
                "HUMAN"
                if output.method != DerivationMethod.DETERMINISTIC_EXTRACTION
                else None
            ),
            "manual_mapping_approval_id": approval.approval_id if approval else None,
            "manual_mapping_approval_hash": approval.approval_hash
            if approval
            else None,
        }
        record = SourceDerivationRecordV2(**body, derivation_hash=content_hash(body))
        derivation_file = f"derivations/{record.derivation_id}.json"
        _write_json(root / derivation_file, asdict(record))
        derivation_rows.append(
            {
                "derivation_id": record.derivation_id,
                "derived_source_id": record.derived_source_id,
                "file": derivation_file,
                "file_sha256": bytes_hash((root / derivation_file).read_bytes()),
                "derivation_hash": record.derivation_hash,
                "record": asdict(record),
            }
        )
    manifest_body = {
        "source_chain_version": SOURCE_CHAIN_VERSION,
        "extraction_policy_version": EXTRACTION_POLICY_VERSION,
        "official_snapshots": tuple(official_rows),
        "local_policy_snapshots": (local_spec,),
        "derived_extracts": tuple(derived_rows),
        "manual_mapping_approvals": tuple(approval_rows),
        "derivations": tuple(derivation_rows),
    }
    manifest = {**manifest_body, "source_chain_hash": content_hash(manifest_body)}
    _write_json(root / "source_chain.json", manifest)
    verify_source_chain(root)
    return manifest


def load_source_chain(root: Path) -> dict[str, Any]:
    verify_source_chain(root)
    return json.loads((root / "source_chain.json").read_text(encoding="utf-8"))


def load_derived_documents(root: Path) -> dict[str, dict[str, Any]]:
    chain = load_source_chain(root)
    return {
        Path(row["file"]).name: json.loads(
            _safe_file(root.resolve(), row["file"]).read_text(encoding="utf-8")
        )
        for row in chain["derived_extracts"]
    }


def load_derivations(root: Path) -> dict[str, SourceDerivationRecordV2]:
    chain = load_source_chain(root)
    return {
        row["derived_source_id"]: derivation_from_dict(row["record"])
        for row in chain["derivations"]
    }


def _extract_iupac(
    specs: dict[str, dict[str, Any]], retrieved_at: str
) -> dict[str, Any]:
    spec = specs["official_iupac_periodic_table_2022"]
    return {
        "source": {
            **_derived_metadata(
                spec,
                retrieved_at,
                "Reviewed 33-element identity mapping bound to the official IUPAC PDF",
            ),
            "derivation_method": DerivationMethod.REVIEWED_MANUAL_MAPPING.value,
        },
        "elements": [
            {
                "atomic_number": z,
                "symbol": symbol,
                "name_en": name,
                "period": period,
                "group": group,
            }
            for z, symbol, name, period, group in REVIEWED_SELECTED_ELEMENTS
        ],
    }


def _extract_ciaaw(
    official_dir: Path, specs: dict[str, dict[str, Any]], retrieved_at: str
) -> dict[str, Any]:
    standard = _table_rows(
        official_dir / specs["official_ciaaw_standard_weights_2024"]["filename"]
    )
    abridged = _table_rows(
        official_dir / specs["official_ciaaw_abridged_weights_2024"]["filename"]
    )
    rows = []
    for z, symbol, name, _, _ in REVIEWED_SELECTED_ELEMENTS:
        standard_row = standard[symbol][1]
        abridged_row = abridged[symbol][1]
        if (
            int(standard_row[0]) != z
            or standard_row[1] != symbol
            or standard_row[2].casefold() != name
            or int(abridged_row[0]) != z
            or abridged_row[1] != symbol
        ):
            raise ValueError(f"CIAAW element identity mismatch for {symbol}")
        standard_notation = standard_row[3].replace(" ", "")
        abridged_notation = abridged_row[3].replace(" ", "")
        abridged_match = re.fullmatch(r"([0-9.]+)±([0-9.]+)", abridged_notation)
        if abridged_match is None:
            raise ValueError(f"invalid CIAAW abridged notation for {symbol}")
        row: dict[str, Any] = {
            "symbol": symbol,
            "abridged_value": _canonical(abridged_match.group(1)),
            "abridged_uncertainty": _canonical(abridged_match.group(2)),
            "abridged_source_notation": abridged_notation,
            "standard_source_notation": standard_notation,
        }
        interval = re.fullmatch(r"\[([0-9.]+),([0-9.]+)\]", standard_notation)
        if interval:
            row.update(
                {
                    "standard_kind": "INTERVAL",
                    "standard_interval_lower": _canonical(interval.group(1)),
                    "standard_interval_upper": _canonical(interval.group(2)),
                    "standard_nominal": None,
                    "standard_uncertainty": None,
                }
            )
        else:
            single = re.fullmatch(r"([0-9.]+)\(([0-9]+)\)", standard_notation)
            if single is None:
                raise ValueError(f"invalid CIAAW standard notation for {symbol}")
            nominal = _canonical(single.group(1))
            places = len(single.group(1).partition(".")[2])
            uncertainty = Decimal(single.group(2)).scaleb(-places)
            row.update(
                {
                    "standard_kind": "SINGLE",
                    "standard_nominal": nominal,
                    "standard_uncertainty": _canonical(uncertainty),
                    "standard_interval_lower": None,
                    "standard_interval_upper": None,
                }
            )
        rows.append(row)
    return {
        "source": {
            "authority": specs["official_ciaaw_standard_weights_2024"]["authority"],
            "title": "CIAAW 2024 deterministic selected atomic-weight extract",
            "version": "2024",
            "standard_url": specs["official_ciaaw_standard_weights_2024"]["url"],
            "abridged_url": specs["official_ciaaw_abridged_weights_2024"]["url"],
            "published_at": "2024-10-23",
            "retrieved_at": retrieved_at,
            "language": "en",
            "license": "Official public reference pages; attribution retained",
            "source_family": "CIAAW_ATOMIC_WEIGHTS_DERIVED",
            "source_kind": "DERIVED_EXTRACT",
            "derivation_method": DerivationMethod.DETERMINISTIC_EXTRACTION.value,
            "limitations": "Selected 33-element extract; uncertainty retained",
        },
        "weights": rows,
    }


def _extract_bipm(
    official_dir: Path, specs: dict[str, dict[str, Any]], retrieved_at: str
) -> dict[str, Any]:
    spec = specs["official_bipm_si_brochure_4_01"]
    raw = (official_dir / spec["filename"]).read_bytes()
    if not raw.startswith(b"%PDF-") or bytes_hash(raw) != spec["sha256"]:
        raise ValueError("BIPM 4.01 PDF snapshot failed verification")
    return {
        "source": {
            **_derived_metadata(
                spec,
                retrieved_at,
                "Reviewed mole-definition mapping from printed page 134",
            ),
            "title": "SI Brochure 9th edition v4.01 reviewed mole mapping",
            "version": "9th edition, version 4.01",
            "doi": "10.59161/AUEZ1291",
            "published_at": "2026-06-04",
            "derivation_method": DerivationMethod.REVIEWED_MANUAL_MAPPING.value,
        },
        "mole": {
            "unit_name": "mole",
            "unit_symbol": "mol",
            "avogadro_constant": "6.02214076E+23",
            "avogadro_unit": "mol^-1",
            "exact": True,
            "entity_scope": ["atoms", "molecules", "formula_units", "generic_entities"],
        },
    }


def _iupac_field_evidence(
    document: dict[str, Any], specs: dict[str, dict[str, Any]], implementation_hash: str
) -> tuple[FieldExtractionEvidence, ...]:
    spec = specs["official_iupac_periodic_table_2022"]
    rows = []
    for index, element in enumerate(document["elements"]):
        for field, value in element.items():
            rows.append(
                _field_evidence(
                    f"/elements/{index}/{field}",
                    value,
                    spec,
                    "PDF_REVIEWED_TABLE_CELL",
                    {
                        "printed_page": 1,
                        "symbol": element["symbol"],
                        "field": field,
                    },
                    None,
                    DerivationMethod.REVIEWED_MANUAL_MAPPING,
                    implementation_hash,
                    HUMAN_REVIEWER,
                )
            )
    return tuple(rows)


def _ciaaw_field_evidence(
    document: dict[str, Any],
    official_dir: Path,
    specs: dict[str, dict[str, Any]],
    implementation_hash: str,
) -> tuple[FieldExtractionEvidence, ...]:
    standard_spec = specs["official_ciaaw_standard_weights_2024"]
    abridged_spec = specs["official_ciaaw_abridged_weights_2024"]
    standard = _table_rows(official_dir / standard_spec["filename"])
    abridged = _table_rows(official_dir / abridged_spec["filename"])
    rows = []
    for index, item in enumerate(document["weights"]):
        symbol = item["symbol"]
        for field, value in item.items():
            is_abridged = field.startswith("abridged")
            spec = abridged_spec if is_abridged else standard_spec
            table_row = abridged[symbol] if is_abridged else standard[symbol]
            rows.append(
                _field_evidence(
                    f"/weights/{index}/{field}",
                    value,
                    spec,
                    "HTML_TABLE_CELL",
                    {
                        "table_header": (
                            "Atomic Number|Symbol|Name|Abridged Standard Atomic Weight"
                            if is_abridged
                            else "Atomic Number|Symbol|Name|Standard Atomic Weight"
                        ),
                        "row_index": table_row[0],
                        "symbol": symbol,
                        "field": field,
                    },
                    content_hash(table_row[1]),
                    DerivationMethod.DETERMINISTIC_EXTRACTION,
                    implementation_hash,
                    None,
                )
            )
    return tuple(rows)


def _bipm_field_evidence(
    document: dict[str, Any], specs: dict[str, dict[str, Any]], implementation_hash: str
) -> tuple[FieldExtractionEvidence, ...]:
    spec = specs["official_bipm_si_brochure_4_01"]
    reviewed_excerpt = (
        "One mole contains exactly 6.022 140 76 x 10^23 elementary entities; "
        "the fixed numerical value is expressed in mol^-1."
    )
    return tuple(
        _field_evidence(
            f"/mole/{field}",
            value,
            spec,
            "PDF_REVIEWED_SPAN",
            {"printed_page": 134, "section": "2.3.6 The mole", "field": field},
            content_hash(reviewed_excerpt),
            DerivationMethod.REVIEWED_MANUAL_MAPPING,
            implementation_hash,
            HUMAN_REVIEWER,
        )
        for field, value in document["mole"].items()
    )


def _ru_field_evidence(
    document: dict[str, Any], local_spec: dict[str, Any], implementation_hash: str
) -> tuple[FieldExtractionEvidence, ...]:
    return tuple(
        _field_evidence(
            f"/names/{symbol}",
            value,
            local_spec,
            "JSON_POINTER",
            {"pointer": f"/names/{symbol}"},
            content_hash(value),
            DerivationMethod.POLICY_TRANSFORMATION,
            implementation_hash,
            HUMAN_REVIEWER,
        )
        for symbol, value in sorted(document["names"].items())
    )


def _field_evidence(
    output_field: str,
    value: Any,
    upstream: dict[str, Any],
    location_type: str,
    locator: dict[str, Any],
    excerpt_hash: str | None,
    method: DerivationMethod,
    implementation_hash: str,
    reviewer: str | None,
) -> FieldExtractionEvidence:
    body = {
        "output_field_name": output_field,
        "output_canonical_value": value,
        "upstream_source_id": upstream["source_id"],
        "upstream_snapshot_hash": upstream["sha256"],
        "upstream_location_type": location_type,
        "upstream_locator": locator,
        "upstream_excerpt_hash": excerpt_hash,
        "extraction_method": method,
        "parser_mapping_implementation_hash": implementation_hash,
        "reviewer": reviewer,
    }
    return FieldExtractionEvidence(**body, evidence_hash=content_hash(body))


def _manual_approval(
    output: _DerivedOutput, upstream_rows: dict[str, dict[str, Any]]
) -> ManualSourceMappingApproval:
    selected_fields = tuple(
        {
            "output_field_name": item.output_field_name,
            "output_canonical_value": item.output_canonical_value,
            "upstream_locator": item.upstream_locator,
            "upstream_excerpt_hash": item.upstream_excerpt_hash,
        }
        for item in output.field_evidence
    )
    upstream = upstream_rows[output.upstream_source_ids[0]]
    body = {
        "approval_id": f"approval_{output.filename.removesuffix('.json')}",
        "official_source_id": upstream["source_id"],
        "official_snapshot_hash": upstream["sha256"],
        "selected_fields": selected_fields,
        "reviewer_identity": HUMAN_REVIEWER,
        "reviewer_identity_type": "HUMAN",
        "review_decision": "APPROVED",
        "policy_version": EXTRACTION_POLICY_VERSION,
        "mapping_hash": content_hash(selected_fields),
        "timestamp": GENERATED_AT,
    }
    return ManualSourceMappingApproval(**body, approval_hash=content_hash(body))


def _upstream_reference(
    source: dict[str, Any], evidence: tuple[FieldExtractionEvidence, ...]
) -> UpstreamSourceReference:
    locations = tuple(
        sorted(
            {
                item.upstream_location_type
                for item in evidence
                if item.upstream_source_id == source["source_id"]
            }
        )
    )
    body = {
        "source_id": source["source_id"],
        "source_kind": source["source_kind"],
        "snapshot_hash": source["sha256"],
        "expected_source_record_hash": None,
        "source_family": source["source_family"],
        "field_location_used": locations,
    }
    return UpstreamSourceReference(**body, reference_hash=content_hash(body))


def _table_rows(path: Path) -> dict[str, tuple[int, list[str]]]:
    parser = _TableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    result = {
        row[1]: (index, row)
        for index, row in enumerate(parser.rows)
        if len(row) >= 4 and row[0].isdigit()
    }
    if not result or not {"H", "C", "Fe"} <= set(result):
        raise ValueError("CIAAW table headers/rows are not recognized")
    return result


def _canonical(value: str | Decimal) -> str:
    limits = DecimalLimits(max_abs=Decimal("1e100"))
    return render_bounded_decimal(parse_bounded_decimal(value, limits), limits)


def _derived_metadata(
    spec: dict[str, Any], retrieved_at: str, limitations: str
) -> dict[str, Any]:
    return {
        "authority": spec["authority"],
        "title": spec["title"] + ", selected mapping",
        "version": spec["version"],
        "url": spec["url"],
        "published_at": spec["published_at"],
        "retrieved_at": retrieved_at,
        "language": "en",
        "license": spec["license"],
        "source_family": spec["source_family"] + "_DERIVED",
        "source_kind": "DERIVED_EXTRACT",
        "limitations": limitations,
    }


def _official_manifest_row(
    root: Path, spec: dict[str, Any], retrieved_at: str
) -> dict[str, Any]:
    row = {
        **spec,
        "file": f"official/{spec['filename']}",
        "retrieved_at": retrieved_at,
        "source_kind": "OFFICIAL_PRIMARY",
    }
    _verify_file(root, row)
    return row


def _local_policy_manifest_row(
    path: Path, policy: dict[str, Any], retrieved_at: str
) -> dict[str, Any]:
    metadata = policy["source"]
    return {
        "source_id": "local_ru_element_names_policy_v1",
        "file": "policy/ru_element_names_policy_v1.json",
        "sha256": bytes_hash(path.read_bytes()),
        "media_type": "application/json",
        "source_kind": "LOCAL_DOCUMENT",
        "title": metadata["title"],
        "authority": metadata["authority"],
        "version": metadata["version"],
        "published_at": metadata["published_at"],
        "retrieved_at": retrieved_at,
        "url": metadata["locator"],
        "source_family": metadata["source_family"],
        "license": metadata["license"],
    }


def _implementation_hash() -> str:
    source = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n")
    return content_hash(
        {
            "module": __name__,
            "source": source,
            "source_chain_version": SOURCE_CHAIN_VERSION,
            "extraction_policy_version": EXTRACTION_POLICY_VERSION,
        }
    )


def _verify_raw(path: Path, spec: dict[str, Any]) -> None:
    if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError(f"missing or oversized official source: {spec['filename']}")
    if bytes_hash(path.read_bytes()) != spec["sha256"]:
        raise ValueError(f"unexpected official source hash: {spec['filename']}")


def _verify_file(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    path = _safe_file(root, row["file"])
    if bytes_hash(path.read_bytes()) != row["sha256"]:
        raise ValueError(f"source snapshot changed: {row['file']}")
    return row


def _resolve_json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("field extraction pointer must be an absolute JSON Pointer")
    current = document
    for raw_part in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw_part):
            raise ValueError("field extraction pointer has invalid escaping")
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                raise ValueError("field extraction pointer is missing")
            current = current[part]
        elif isinstance(current, list):
            if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                raise ValueError("field extraction array pointer is invalid")
            index = int(part)
            if index >= len(current):
                raise ValueError("field extraction pointer is missing")
            current = current[index]
        else:
            raise TypeError("field extraction pointer traverses a scalar")
    return current


def _production_leaf_pointers(document: dict[str, Any]) -> set[str]:
    pointers: set[str] = set()

    def visit(value: Any, pointer: str) -> None:
        if pointer == "/source" or pointer.startswith("/source/"):
            return
        if isinstance(value, dict):
            for key, child in value.items():
                escaped = key.replace("~", "~0").replace("/", "~1")
                visit(child, f"{pointer}/{escaped}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{pointer}/{index}")
        else:
            pointers.add(pointer)

    visit(document, "")
    return pointers


def _safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f"missing or unsafe source-chain file: {relative}")
    return path


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
