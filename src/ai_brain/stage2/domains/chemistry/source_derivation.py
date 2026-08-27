"""Offline-verifiable official-source and deterministic-extract chain for M-28.1."""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import asdict
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.models import SourceDerivationRecord
from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage2.trusted_decimal import (
    DecimalLimits,
    parse_bounded_decimal,
    render_bounded_decimal,
)

SOURCE_CHAIN_VERSION = "2.0"
EXTRACTION_POLICY_VERSION = "deterministic-selected-chemistry-fields-v2"
MAX_SOURCE_BYTES = 8_000_000

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

SELECTED_ELEMENTS: tuple[tuple[int, str, str, int, int], ...] = (
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


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def verify_source_chain(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "source_chain.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    official = tuple(_verify_file(root, row) for row in manifest["official_snapshots"])
    extracts = tuple(_verify_file(root, row) for row in manifest["derived_extracts"])
    derivations = []
    current_extractor_hash = bytes_hash(Path(__file__).read_bytes())
    for row in manifest["derivations"]:
        path = _safe_file(root, row["file"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        digest = payload.pop("derivation_hash")
        if content_hash(payload) != digest or digest != row["derivation_hash"]:
            raise ValueError(f"source derivation changed: {row['file']}")
        if payload["extractor_implementation_hash"] != current_extractor_hash:
            raise ValueError("source derivation extractor implementation changed")
        official_hashes = tuple(item["sha256"] for item in official)
        if not set(payload["official_snapshot_hashes"]) <= set(official_hashes):
            raise ValueError("derivation references an unknown official snapshot")
        extract_hashes = {item["sha256"] for item in extracts}
        if payload["derived_extract_hash"] not in extract_hashes:
            raise ValueError("derivation references an unknown derived extract")
        derivations.append({**payload, "derivation_hash": digest})
    body = dict(manifest)
    digest = body.pop("source_chain_hash")
    if content_hash(body) != digest:
        raise ValueError("source chain manifest hash mismatch")
    return {
        "status": "VERIFIED",
        "official_count": len(official),
        "derived_count": len(extracts),
        "derivation_count": len(derivations),
        "source_chain_hash": digest,
    }


def build_derived_sources(root: Path, *, retrieved_at: str) -> dict[str, Any]:
    root = root.resolve()
    official_dir = root / "official"
    derived_dir = root / "derived"
    derivation_dir = root / "derivations"
    derived_dir.mkdir(parents=True, exist_ok=True)
    derivation_dir.mkdir(parents=True, exist_ok=True)
    specs = {row["source_id"]: row for row in OFFICIAL_SOURCE_SPECS}
    for spec in OFFICIAL_SOURCE_SPECS:
        _verify_raw(official_dir / spec["filename"], spec)

    outputs: list[
        tuple[str, dict[str, Any], tuple[str, ...], tuple[dict[str, Any], ...]]
    ] = []
    outputs.append(
        (
            "iupac_elements_2022.json",
            _extract_iupac(specs, retrieved_at),
            ("official_iupac_periodic_table_2022",),
            tuple(
                {
                    "symbol": symbol,
                    "fields": ("atomic_number", "name_en", "period", "group"),
                }
                for _, symbol, _, _, _ in SELECTED_ELEMENTS
            ),
        )
    )
    outputs.append(
        (
            "ciaaw_atomic_weights_2024.json",
            _extract_ciaaw(official_dir, specs, retrieved_at),
            (
                "official_ciaaw_standard_weights_2024",
                "official_ciaaw_abridged_weights_2024",
            ),
            tuple(
                {"symbol": symbol, "fields": ("standard", "abridged", "uncertainty")}
                for _, symbol, _, _, _ in SELECTED_ELEMENTS
            ),
        )
    )
    outputs.append(
        (
            "bipm_si_mole_2026.json",
            _extract_bipm(official_dir, specs, retrieved_at),
            ("official_bipm_si_brochure_4_01",),
            (
                {
                    "json_pointer": "/mole/avogadro_constant",
                    "source_text": "exact mole definition",
                },
            ),
        )
    )
    policy_path = root / "policy" / "ru_element_names_policy_v1.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    outputs.append(
        (
            "ru_element_names_policy_v1.json",
            {
                **policy,
                "source": {
                    **policy["source"],
                    "source_kind": "DETERMINISTIC_DERIVED_EXTRACT",
                },
            },
            ("local_ru_element_names_policy_v1",),
            tuple(
                {"symbol": key, "field": "name_ru"} for key in sorted(policy["names"])
            ),
        )
    )

    extractor_hash = bytes_hash(
        Path(inspect.getsourcefile(build_derived_sources) or __file__).read_bytes()
    )
    official_rows = [
        _official_manifest_row(root, row, retrieved_at) for row in OFFICIAL_SOURCE_SPECS
    ]
    derived_rows = []
    derivation_rows = []
    for filename, document, source_ids, mapping in outputs:
        path = derived_dir / filename
        _write_json(path, document)
        digest = bytes_hash(path.read_bytes())
        source_id = f"derived_{filename.removesuffix('.json')}"
        derived_rows.append(
            {
                "source_id": source_id,
                "file": f"derived/{filename}",
                "sha256": digest,
                "media_type": "application/json",
                "source_kind": "DETERMINISTIC_DERIVED_EXTRACT",
            }
        )
        upstream = tuple(
            row["sha256"] if row["source_id"] in source_ids else ""
            for row in official_rows
            if row["source_id"] in source_ids
        )
        if source_ids == ("local_ru_element_names_policy_v1",):
            upstream = (bytes_hash(policy_path.read_bytes()),)
        body = {
            "derivation_id": f"derivation_{filename.removesuffix('.json')}",
            "official_source_ids": source_ids,
            "official_snapshot_hashes": upstream,
            "derived_extract_source_id": source_id,
            "derived_extract_hash": digest,
            "extractor_module": __name__,
            "extractor_implementation_hash": extractor_hash,
            "extraction_policy_version": EXTRACTION_POLICY_VERSION,
            "selected_row_field_mapping": mapping,
            "generated_at": "2026-08-27T00:00:00Z",
            "reviewer": "m281-deterministic-source-extractor",
        }
        record = SourceDerivationRecord(**body, derivation_hash=content_hash(body))
        derivation_file = f"derivations/{record.derivation_id}.json"
        _write_json(root / derivation_file, asdict(record))
        derivation_rows.append(
            {
                "derivation_id": record.derivation_id,
                "file": derivation_file,
                "derivation_hash": record.derivation_hash,
            }
        )
    local_row = {
        "source_id": "local_ru_element_names_policy_v1",
        "file": "policy/ru_element_names_policy_v1.json",
        "sha256": bytes_hash(policy_path.read_bytes()),
        "media_type": "application/json",
        "source_kind": "LOCAL_DOCUMENT",
        "title": policy["source"]["title"],
        "authority": policy["source"]["authority"],
        "version": policy["source"]["version"],
        "published_at": policy["source"]["published_at"],
        "retrieved_at": retrieved_at,
        "url": policy["source"]["locator"],
        "source_family": policy["source"]["source_family"],
        "license": policy["source"]["license"],
    }
    manifest_body = {
        "source_chain_version": SOURCE_CHAIN_VERSION,
        "official_snapshots": tuple(official_rows) + (local_row,),
        "derived_extracts": tuple(derived_rows),
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
    result = {}
    for row in chain["derived_extracts"]:
        result[Path(row["file"]).name] = json.loads(
            _safe_file(root.resolve(), row["file"]).read_text(encoding="utf-8")
        )
    return result


def load_derivations(root: Path) -> dict[str, SourceDerivationRecord]:
    chain = load_source_chain(root)
    records = {}
    for row in chain["derivations"]:
        payload = json.loads(
            _safe_file(root.resolve(), row["file"]).read_text(encoding="utf-8")
        )
        payload["official_source_ids"] = tuple(payload["official_source_ids"])
        payload["official_snapshot_hashes"] = tuple(payload["official_snapshot_hashes"])
        payload["selected_row_field_mapping"] = tuple(
            payload["selected_row_field_mapping"]
        )
        record = SourceDerivationRecord(**payload)
        records[record.derived_extract_source_id] = record
    return records


def _extract_iupac(
    specs: dict[str, dict[str, Any]], retrieved_at: str
) -> dict[str, Any]:
    spec = specs["official_iupac_periodic_table_2022"]
    return {
        "source": _derived_metadata(
            spec,
            retrieved_at,
            "Selected identity fields from the official IUPAC periodic table",
        ),
        "elements": [
            {
                "atomic_number": z,
                "symbol": symbol,
                "name_en": name,
                "period": period,
                "group": group,
            }
            for z, symbol, name, period, group in SELECTED_ELEMENTS
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
    for z, symbol, name, _, _ in SELECTED_ELEMENTS:
        standard_row = standard[symbol]
        abridged_row = abridged[symbol]
        if int(standard_row[0]) != z or standard_row[2].casefold() != name:
            raise ValueError(f"CIAAW standard identity mismatch for {symbol}")
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
            "title": "Standard Atomic Weights 2024 and Abridged Standard Atomic Weights 2024, deterministic selected extract",
            "version": "2024",
            "standard_url": specs["official_ciaaw_standard_weights_2024"]["url"],
            "abridged_url": specs["official_ciaaw_abridged_weights_2024"]["url"],
            "published_at": "2024-10-23",
            "retrieved_at": retrieved_at,
            "language": "en",
            "license": "Official public reference pages; attribution retained",
            "source_family": "CIAAW_ATOMIC_WEIGHTS_DERIVED",
            "source_kind": "DETERMINISTIC_DERIVED_EXTRACT",
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
                spec, retrieved_at, "Mole definition and exact Avogadro constant"
            ),
            "title": "The International System of Units (SI), 9th edition, version 4.01, selected mole extract",
            "version": "9th edition, version 4.01",
            "doi": "10.59161/AUEZ1291",
            "published_at": "2026-06-04",
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


def _table_rows(path: Path) -> dict[str, list[str]]:
    parser = _TableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return {row[1]: row for row in parser.rows if len(row) >= 4 and row[0].isdigit()}


def _canonical(value: str | Decimal) -> str:
    limits = DecimalLimits(max_abs=Decimal("1e100"))
    return render_bounded_decimal(parse_bounded_decimal(value, limits), limits)


def _derived_metadata(
    spec: dict[str, Any], retrieved_at: str, limitations: str
) -> dict[str, Any]:
    return {
        "authority": spec["authority"],
        "title": spec["title"] + ", deterministic selected extract",
        "version": spec["version"],
        "url": spec["url"],
        "published_at": spec["published_at"],
        "retrieved_at": retrieved_at,
        "language": "en",
        "license": spec["license"],
        "source_family": spec["source_family"] + "_DERIVED",
        "source_kind": "DETERMINISTIC_DERIVED_EXTRACT",
        "limitations": limitations,
    }


def _official_manifest_row(
    root: Path, spec: dict[str, Any], retrieved_at: str
) -> dict[str, Any]:
    return {
        **spec,
        "file": f"official/{spec['filename']}",
        "retrieved_at": retrieved_at,
        "source_kind": "OFFICIAL_PRIMARY",
    }


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
