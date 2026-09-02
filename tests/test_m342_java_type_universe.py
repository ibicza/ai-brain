from __future__ import annotations

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_type_universe import (
    JavaResolutionKind,
    build_java_type_universe,
    resolve_java_type,
    verify_java_type_universe,
)


def _resolve(
    source_type: str,
    *,
    source_symbols=(),
    package_name="example.current",
    receiver_type="example.current.Outer.Inner",
    explicit_imports=None,
    wildcard_imports=(),
    type_variables=None,
):
    universe = build_java_type_universe(source_symbols)
    result = resolve_java_type(
        source_type,
        universe=universe,
        package_name=package_name,
        receiver_type=receiver_type,
        explicit_imports=explicit_imports or {},
        wildcard_imports=wildcard_imports,
        type_variables=type_variables or {},
    )
    body = {
        "source_type": result.source_type,
        "erased_source_type": result.erased_source_type,
        "resolved_type": result.resolved_type,
        "resolution_kind": result.resolution_kind,
        "candidates": result.candidates,
        "array_dimensions": result.array_dimensions,
        "universe_manifest_hash": result.universe_manifest_hash,
    }
    assert result.receipt_hash == content_hash(body)
    verify_java_type_universe(universe)
    return result


def test_resolution_precedence_is_sealed_and_receipted():
    symbols = (
        "example.current.Outer",
        "example.current.Outer.Inner",
        "example.current.Outer.Inner.Local",
        "example.current.SamePackage",
    )
    assert (
        _resolve("int", source_symbols=symbols).resolution_kind
        is JavaResolutionKind.PRIMITIVE
    )
    variable = _resolve(
        "T", source_symbols=symbols, type_variables={"T": "java.lang.Number"}
    )
    assert (variable.resolution_kind, variable.resolved_type) == (
        JavaResolutionKind.TYPE_VARIABLE,
        "java.lang.Number",
    )
    lexical = _resolve("Local", source_symbols=symbols)
    assert (lexical.resolution_kind, lexical.resolved_type) == (
        JavaResolutionKind.LEXICAL,
        "example.current.Outer.Inner.Local",
    )
    imported = _resolve(
        "List<String>",
        source_symbols=symbols,
        explicit_imports={"List": ("java.util.List",)},
    )
    assert (imported.resolution_kind, imported.resolved_type) == (
        JavaResolutionKind.EXPLICIT_IMPORT,
        "java.util.List",
    )
    same_package = _resolve("SamePackage", source_symbols=symbols)
    assert same_package.resolution_kind is JavaResolutionKind.SAME_PACKAGE
    assert (
        _resolve("String", source_symbols=symbols).resolution_kind
        is JavaResolutionKind.JAVA_LANG
    )
    wildcard = _resolve("List", source_symbols=symbols, wildcard_imports=("java.util",))
    assert wildcard.resolution_kind is JavaResolutionKind.WILDCARD_IMPORT


def test_missing_explicit_fqn_and_foreign_simple_names_abstain():
    missing_import = _resolve(
        "List", explicit_imports={"List": ("missing.package.List",)}
    )
    assert (missing_import.resolution_kind, missing_import.resolved_type) == (
        JavaResolutionKind.UNRESOLVED,
        None,
    )
    assert missing_import.candidates == ("missing.package.List",)
    assert _resolve("missing.package.Type").resolved_type is None
    assert _resolve("ZoneId", package_name="foreign.package").resolved_type is None


def test_wildcard_ambiguity_and_invalid_duplicate_imports_abstain():
    source = ("alpha.Value", "beta.Value")
    wildcard = _resolve(
        "Value", source_symbols=source, wildcard_imports=("alpha", "beta")
    )
    assert wildcard.resolution_kind is JavaResolutionKind.AMBIGUOUS
    duplicate_import = _resolve(
        "Date",
        explicit_imports={"Date": ("java.sql.Date", "java.util.Date")},
    )
    assert duplicate_import.resolution_kind is JavaResolutionKind.AMBIGUOUS


def test_varargs_and_arrays_are_counted_exactly_once():
    varargs = _resolve("String...", package_name="example")
    array = _resolve("String[]", package_name="example")
    mixed = _resolve("String[]...", package_name="example")
    assert (varargs.resolved_type, varargs.array_dimensions) == (
        "java.lang.String[]",
        1,
    )
    assert (array.resolved_type, array.array_dimensions) == (
        "java.lang.String[]",
        1,
    )
    assert (mixed.resolved_type, mixed.array_dimensions) == (
        "java.lang.String[][]",
        2,
    )
