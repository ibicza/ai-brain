"""Sealed Java 21 and source-bundle symbol universe with receipt-bound resolution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

_DATA = Path(__file__).with_name("data") / "java21_symbols.json"
_PRIMITIVES = {
    "boolean",
    "byte",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "void",
}


class JavaResolutionKind(StrEnum):
    PRIMITIVE = "PRIMITIVE"
    TYPE_VARIABLE = "TYPE_VARIABLE"
    LEXICAL = "LEXICAL"
    EXPLICIT_IMPORT = "EXPLICIT_IMPORT"
    SAME_PACKAGE = "SAME_PACKAGE"
    JAVA_LANG = "JAVA_LANG"
    WILDCARD_IMPORT = "WILDCARD_IMPORT"
    FULLY_QUALIFIED = "FULLY_QUALIFIED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class JavaSymbolInventoryManifest:
    schema_version: int
    inventory_id: str
    release: int
    source_kind: str
    source_ct_sym_sha256: str
    symbol_count: int
    symbols_hash: str
    artifact_bytes_hash: str
    manifest_hash: str


@dataclass(frozen=True)
class JavaTypeUniverse:
    platform_inventory: JavaSymbolInventoryManifest
    source_symbols: tuple[str, ...]
    source_symbols_hash: str
    symbols: tuple[str, ...]
    symbol_count: int
    manifest_hash: str


@dataclass(frozen=True)
class JavaTypeResolution:
    source_type: str
    erased_source_type: str
    resolved_type: str | None
    resolution_kind: JavaResolutionKind
    candidates: tuple[str, ...]
    array_dimensions: int
    universe_manifest_hash: str
    receipt_hash: str


def load_java21_inventory() -> tuple[JavaSymbolInventoryManifest, tuple[str, ...]]:
    raw = _DATA.read_bytes()
    row = json.loads(raw.decode("utf-8"))
    claimed = row.pop("manifest_hash")
    if content_hash(row) != claimed or row["release"] != 21:
        raise ValueError("Java 21 platform inventory manifest mismatch")
    symbols = tuple(row.pop("symbols"))
    if row["symbol_count"] != len(symbols) or tuple(sorted(set(symbols))) != symbols:
        raise ValueError("Java 21 platform inventory is not canonical")
    body = {
        **row,
        "symbols_hash": content_hash(symbols),
        "artifact_bytes_hash": bytes_hash(raw),
    }
    manifest = JavaSymbolInventoryManifest(**body, manifest_hash=content_hash(body))
    return manifest, symbols


def build_java_type_universe(source_symbols) -> JavaTypeUniverse:
    platform, platform_symbols = load_java21_inventory()
    source = tuple(sorted(set(source_symbols)))
    symbols = tuple(sorted(set(platform_symbols).union(source)))
    body = {
        "platform_inventory": platform,
        "source_symbols": source,
        "source_symbols_hash": content_hash(source),
        "symbols": symbols,
        "symbol_count": len(symbols),
    }
    return JavaTypeUniverse(**body, manifest_hash=content_hash(body))


def verify_java_type_universe(universe: JavaTypeUniverse) -> None:
    rebuilt = build_java_type_universe(universe.source_symbols)
    if rebuilt != universe:
        raise ValueError("Java type universe is not reproducible")


def resolve_java_type(
    source_type: str,
    *,
    universe: JavaTypeUniverse,
    package_name: str | None,
    receiver_type: str,
    explicit_imports: dict[str, tuple[str, ...]],
    wildcard_imports: tuple[str, ...],
    type_variables: dict[str, str],
) -> JavaTypeResolution:
    cleaned, dimensions = _type_shape(source_type)
    erased = _erase_generics(cleaned).strip()
    if erased.startswith("? extends "):
        erased = erased[10:].strip()
    elif erased.startswith("? super ") or erased == "?":
        erased = "Object"
    symbols = set(universe.symbols)
    kind = JavaResolutionKind.UNRESOLVED
    candidates: tuple[str, ...] = ()
    resolved = None
    if erased in _PRIMITIVES:
        resolved, kind = erased, JavaResolutionKind.PRIMITIVE
    elif erased in type_variables:
        bound = type_variables[erased] or "Object"
        bound_resolution = resolve_java_type(
            bound,
            universe=universe,
            package_name=package_name,
            receiver_type=receiver_type,
            explicit_imports=explicit_imports,
            wildcard_imports=wildcard_imports,
            type_variables={},
        )
        resolved = bound_resolution.resolved_type or "java.lang.Object"
        kind = JavaResolutionKind.TYPE_VARIABLE
        candidates = (resolved,)
    elif _looks_fully_qualified(erased):
        matches = _qualified_candidates(erased, symbols)
        if len(matches) == 1:
            resolved, kind, candidates = (
                matches[0],
                JavaResolutionKind.FULLY_QUALIFIED,
                matches,
            )
        elif len(matches) > 1:
            kind, candidates = JavaResolutionKind.AMBIGUOUS, matches
    else:
        parts = erased.replace("$", ".").split(".")
        head, tail = parts[0], parts[1:]
        lexical = _lexical_candidates(head, tail, receiver_type, package_name, symbols)
        if len(lexical) == 1:
            resolved, kind, candidates = (
                lexical[0],
                JavaResolutionKind.LEXICAL,
                lexical,
            )
        elif len(lexical) > 1:
            kind, candidates = JavaResolutionKind.AMBIGUOUS, lexical
        else:
            declared_imports = explicit_imports.get(head, ())
            imported = tuple(
                sorted(
                    value
                    for base in declared_imports
                    for value in _qualified_candidates(".".join((base, *tail)), symbols)
                )
            )
            if len(declared_imports) == 1 and len(imported) == 1:
                resolved, kind, candidates = (
                    imported[0],
                    JavaResolutionKind.EXPLICIT_IMPORT,
                    imported,
                )
            elif len(declared_imports) > 1:
                kind = JavaResolutionKind.AMBIGUOUS
                candidates = tuple(sorted(declared_imports))
            elif head in explicit_imports:
                candidates = tuple(sorted(declared_imports))
            else:
                same_package = _qualified_candidates(
                    ".".join(item for item in (package_name, erased) if item),
                    symbols,
                )
                if len(same_package) == 1:
                    resolved, kind, candidates = (
                        same_package[0],
                        JavaResolutionKind.SAME_PACKAGE,
                        same_package,
                    )
                elif len(same_package) > 1:
                    kind, candidates = JavaResolutionKind.AMBIGUOUS, same_package
                else:
                    java_lang = _qualified_candidates(f"java.lang.{erased}", symbols)
                    if len(java_lang) == 1:
                        resolved, kind, candidates = (
                            java_lang[0],
                            JavaResolutionKind.JAVA_LANG,
                            java_lang,
                        )
                    else:
                        wildcard = tuple(
                            sorted(
                                {
                                    value
                                    for package in wildcard_imports
                                    for value in _qualified_candidates(
                                        f"{package}.{erased}", symbols
                                    )
                                }
                            )
                        )
                        if len(wildcard) == 1:
                            resolved, kind, candidates = (
                                wildcard[0],
                                JavaResolutionKind.WILDCARD_IMPORT,
                                wildcard,
                            )
                        elif len(wildcard) > 1:
                            kind, candidates = JavaResolutionKind.AMBIGUOUS, wildcard
    if resolved is not None:
        resolved += "[]" * dimensions
    body = {
        "source_type": source_type,
        "erased_source_type": erased,
        "resolved_type": resolved,
        "resolution_kind": kind,
        "candidates": candidates,
        "array_dimensions": dimensions,
        "universe_manifest_hash": universe.manifest_hash,
    }
    return JavaTypeResolution(**body, receipt_hash=content_hash(body))


def _type_shape(value: str) -> tuple[str, int]:
    text = re.sub(r"@[\w.]+(?:\s*\([^)]*\))?\s*", "", value)
    text = " ".join(text.split()).replace(" []", "[]")
    dimensions = 0
    if text.endswith("..."):
        dimensions += 1
        text = text[:-3].rstrip()
    while text.endswith("[]"):
        dimensions += 1
        text = text[:-2].rstrip()
    return text, dimensions


def _erase_generics(value: str) -> str:
    result = []
    depth = 0
    for character in value:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            result.append(character)
    return "".join(result)


def _looks_fully_qualified(value: str) -> bool:
    head = value.split(".", 1)[0]
    return "." in value and bool(head) and head[0].islower()


def _qualified_candidates(value: str, symbols: set[str]) -> tuple[str, ...]:
    normalized = value.replace("$", ".")
    return (normalized,) if normalized in symbols else ()


def _lexical_candidates(head, tail, receiver_type, package_name, symbols):
    receiver = receiver_type.replace("$", ".")
    package_prefix = f"{package_name}." if package_name else ""
    type_name = receiver.removeprefix(package_prefix)
    pieces = type_name.split(".")
    result = set()
    for size in range(len(pieces), 0, -1):
        prefix = ".".join((*([package_name] if package_name else []), *pieces[:size]))
        candidate = ".".join((prefix, head, *tail))
        if candidate in symbols:
            result.add(candidate)
            break
        if pieces[size - 1] == head:
            candidate = ".".join((prefix, *tail))
            if candidate in symbols:
                result.add(candidate)
                break
    return tuple(sorted(result))
