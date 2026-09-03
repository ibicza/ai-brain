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
class JavaSymbolMetadata:
    binary_name: str
    package_name: str
    module_name: str | None
    symbol_kind: str
    top_level_binary_name: str
    enclosing_binary_name: str | None
    access: str
    enclosing_access: str
    package_exported: bool
    origin: str
    receipt_hash: str


@dataclass(frozen=True)
class JavaTypeUniverse:
    platform_inventory: JavaSymbolInventoryManifest
    source_symbols: tuple[str, ...]
    source_symbols_hash: str
    symbols: tuple[str, ...]
    symbol_metadata: tuple[JavaSymbolMetadata, ...]
    symbol_metadata_hash: str
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
    symbol_receipt_hash: str | None
    complete_receipt_hash: str
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
    source_metadata = tuple(
        item if isinstance(item, JavaSymbolMetadata) else source_symbol_metadata(item)
        for item in source_symbols
    )
    source_by_name = {item.binary_name: item for item in source_metadata}
    source = tuple(sorted(source_by_name))
    symbols = tuple(sorted(set(platform_symbols).union(source)))
    metadata = tuple(
        sorted(
            (
                *(_platform_symbol_metadata(item) for item in platform_symbols),
                *source_by_name.values(),
            ),
            key=lambda item: item.binary_name,
        )
    )
    body = {
        "platform_inventory": platform,
        "source_symbols": source,
        "source_symbols_hash": content_hash(source),
        "symbols": symbols,
        "symbol_metadata": metadata,
        "symbol_metadata_hash": content_hash(metadata),
        "symbol_count": len(symbols),
    }
    return JavaTypeUniverse(**body, manifest_hash=content_hash(body))


def verify_java_type_universe(universe: JavaTypeUniverse) -> None:
    rebuilt = build_java_type_universe(
        item for item in universe.symbol_metadata if item.origin == "SOURCE"
    )
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
    lexical_owner_types: tuple[str, ...] = (),
) -> JavaTypeResolution:
    cleaned, dimensions = _type_shape(source_type)
    erased = _erase_generics(cleaned).strip()
    if erased.startswith("? extends "):
        erased = erased[10:].strip()
    elif erased.startswith("? super ") or erased == "?":
        erased = "Object"
    symbols = set(universe.symbols)
    metadata = {item.binary_name: item for item in universe.symbol_metadata}
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
            lexical_owner_types=lexical_owner_types,
        )
        resolved = bound_resolution.resolved_type
        kind = JavaResolutionKind.TYPE_VARIABLE
        candidates = (resolved,) if resolved is not None else ()
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
        lexical = _lexical_candidates(
            head,
            tail,
            receiver_type,
            package_name,
            symbols,
            lexical_owner_types,
        )
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
    if (
        resolved is not None
        and resolved not in _PRIMITIVES
        and not _is_accessible(
            metadata[resolved], package_name=package_name, receiver_type=receiver_type
        )
    ):
        candidates = (resolved,)
        resolved = None
        kind = JavaResolutionKind.UNRESOLVED
    symbol_receipt_hash = (
        metadata[resolved].receipt_hash
        if resolved is not None and resolved not in _PRIMITIVES
        else None
    )
    if resolved is not None:
        resolved += "[]" * dimensions
    legacy_body = {
        "source_type": source_type,
        "erased_source_type": erased,
        "resolved_type": resolved,
        "resolution_kind": kind,
        "candidates": candidates,
        "array_dimensions": dimensions,
        "universe_manifest_hash": universe.manifest_hash,
    }
    body = {
        **legacy_body,
        "symbol_receipt_hash": symbol_receipt_hash,
    }
    return JavaTypeResolution(
        **body,
        complete_receipt_hash=content_hash(body),
        receipt_hash=content_hash(legacy_body),
    )


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


def _lexical_candidates(
    head, tail, receiver_type, package_name, symbols, lexical_owner_types=()
):
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
    for owner in lexical_owner_types:
        candidate = ".".join((owner.replace("$", "."), head, *tail))
        if candidate in symbols:
            result.add(candidate)
            break
    return tuple(sorted(result))


def source_symbol_metadata(
    binary_name: str,
    *,
    symbol_kind: str = "class",
    access: str = "PUBLIC",
    enclosing_access: str = "PUBLIC",
    local_type: bool = False,
) -> JavaSymbolMetadata:
    package, top, enclosing = _name_parts(binary_name)
    body = {
        "binary_name": binary_name.replace("$", "."),
        "package_name": package,
        "module_name": None,
        "symbol_kind": "local" if local_type else symbol_kind,
        "top_level_binary_name": top,
        "enclosing_binary_name": enclosing,
        "access": access,
        "enclosing_access": enclosing_access,
        "package_exported": True,
        "origin": "SOURCE",
    }
    return JavaSymbolMetadata(**body, receipt_hash=content_hash(body))


def _platform_symbol_metadata(binary_name: str) -> JavaSymbolMetadata:
    package, top, enclosing = _name_parts(binary_name)
    exported = not (
        binary_name.startswith(("sun.", "jdk.internal.")) or ".internal." in binary_name
    )
    module = (
        "java.base"
        if binary_name.startswith(
            (
                "java.lang.",
                "java.util.",
                "java.io.",
                "java.net.",
                "java.nio.",
                "java.time.",
                "java.math.",
                "java.security.",
                "java.text.",
            )
        )
        else "java.platform"
    )
    body = {
        "binary_name": binary_name.replace("$", "."),
        "package_name": package,
        "module_name": module,
        "symbol_kind": "TYPE",
        "top_level_binary_name": top,
        "enclosing_binary_name": enclosing,
        "access": "PUBLIC",
        "enclosing_access": "PUBLIC",
        "package_exported": exported,
        "origin": "JAVA21_PLATFORM",
    }
    return JavaSymbolMetadata(**body, receipt_hash=content_hash(body))


def _name_parts(binary_name: str) -> tuple[str, str, str | None]:
    value = binary_name.replace("$", ".")
    parts = value.split(".")
    first_type = next(
        (index for index, part in enumerate(parts) if part and part[0].isupper()),
        max(0, len(parts) - 1),
    )
    package = ".".join(parts[:first_type])
    type_parts = parts[first_type:]
    top = ".".join((*parts[:first_type], type_parts[0]))
    enclosing = (
        ".".join((*parts[:first_type], *type_parts[:-1]))
        if len(type_parts) > 1
        else None
    )
    return package, top, enclosing


def _is_accessible(
    symbol: JavaSymbolMetadata,
    *,
    package_name: str | None,
    receiver_type: str,
) -> bool:
    if not symbol.package_exported or symbol.symbol_kind == "local":
        return False
    if (
        symbol.enclosing_access == "PRIVATE"
        and not receiver_type.startswith(f"{symbol.enclosing_binary_name}.")
        and receiver_type != symbol.enclosing_binary_name
    ):
        return False
    if symbol.access == "PRIVATE":
        return (
            receiver_type == symbol.enclosing_binary_name
            or receiver_type.startswith(f"{symbol.enclosing_binary_name}.")
        )
    if symbol.access == "PACKAGE":
        return package_name == symbol.package_name
    return True
