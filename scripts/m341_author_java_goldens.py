"""Author sealed Java declaration goldens without importing production code.

This is deliberately a separate implementation.  Acceptance loads the checked-in
JSON and never invokes this authoring program.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_java
from tree_sitter import Language, Parser

TYPE_NODES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
TYPE_BODIES = {
    "class_body",
    "interface_body",
    "enum_body",
    "annotation_type_body",
}
METHOD_NODES = {
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "compact_constructor_declaration": "constructor",
}
PRIMITIVES = {
    "boolean": "Z",
    "byte": "B",
    "char": "C",
    "double": "D",
    "float": "F",
    "int": "I",
    "long": "J",
    "short": "S",
    "void": "V",
}
JAVA_LANG = {
    "Appendable",
    "ArithmeticException",
    "AutoCloseable",
    "Boolean",
    "Byte",
    "CharSequence",
    "Character",
    "Class",
    "ClassLoader",
    "Cloneable",
    "Comparable",
    "Deprecated",
    "Double",
    "Enum",
    "Error",
    "Exception",
    "Float",
    "IllegalArgumentException",
    "IllegalStateException",
    "IndexOutOfBoundsException",
    "Integer",
    "Iterable",
    "Long",
    "Math",
    "Number",
    "Object",
    "Override",
    "Record",
    "Runnable",
    "RuntimeException",
    "Short",
    "String",
    "StringBuilder",
    "System",
    "Throwable",
    "UnsupportedOperationException",
    "Void",
}


@dataclass(frozen=True)
class Source:
    path: Path
    raw: bytes
    root: object
    package: str | None
    imports: dict[str, tuple[str, ...]]


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def content_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text(node, raw: bytes) -> str:
    return raw[node.start_byte : node.end_byte].decode("utf-8")


def package_name(root, raw: bytes) -> str | None:
    declaration = next(
        (item for item in root.named_children if item.type == "package_declaration"),
        None,
    )
    if declaration is None:
        return None
    name = next(
        (
            item
            for item in declaration.named_children
            if item.type in {"identifier", "scoped_identifier"}
        ),
        None,
    )
    return text(name, raw) if name is not None else None


def imports(root, raw: bytes) -> dict[str, tuple[str, ...]]:
    values: dict[str, set[str]] = {}
    for declaration in root.named_children:
        if declaration.type != "import_declaration":
            continue
        value = text(declaration, raw).removeprefix("import").strip().rstrip(";")
        value = value.removeprefix("static").strip()
        if value.endswith(".*"):
            continue
        values.setdefault(value.rsplit(".", 1)[-1], set()).add(value)
    return {key: tuple(sorted(items)) for key, items in values.items()}


def type_variables(node, raw: bytes) -> tuple[tuple[str, str], ...]:
    container = next(
        (item for item in node.named_children if item.type == "type_parameters"),
        None,
    )
    if container is None:
        return ()
    result = []
    for parameter in container.named_children:
        if parameter.type != "type_parameter":
            continue
        name = text(parameter.named_children[0], raw)
        bound_node = next(
            (item for item in parameter.named_children if item.type == "type_bound"),
            None,
        )
        bound = (
            text(bound_node.named_children[0], raw)
            if bound_node is not None and bound_node.named_children
            else "Object"
        )
        result.append((name, bound))
    return tuple(result)


def parameter_parts(container, raw: bytes):
    if container is None:
        return ()
    result = []
    for parameter in container.named_children:
        if parameter.type not in {
            "formal_parameter",
            "spread_parameter",
            "receiver_parameter",
        }:
            continue
        varargs = parameter.type == "spread_parameter"
        name_node = parameter.child_by_field_name("name")
        type_node = parameter.child_by_field_name("type")
        declarator = next(
            (
                item
                for item in parameter.named_children
                if item.type == "variable_declarator"
            ),
            None,
        )
        if name_node is None and declarator is not None:
            name_node = declarator.child_by_field_name("name")
        if type_node is None:
            type_node = next(
                (
                    item
                    for item in parameter.named_children
                    if item is not declarator and item.type != "modifiers"
                ),
                None,
            )
        if name_node is None or type_node is None:
            return None
        result.append((text(type_node, raw) + ("..." if varargs else ""), varargs))
    return tuple(result)


def clean_type(value: str) -> str:
    value = re.sub(r"@[\w.]+(?:\s*\([^)]*\))?\s*", "", value)
    return " ".join(value.split()).replace(" []", "[]")


def erase_generics(value: str) -> str:
    output = []
    depth = 0
    for character in value:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            output.append(character)
    return "".join(output)


def resolve_type(value, declaration, variables, known_types):
    value = clean_type(value)
    dimensions = 0
    if value.endswith("..."):
        dimensions += 1
        value = value[:-3]
    while value.endswith("[]"):
        dimensions += 1
        value = value[:-2]
    value = erase_generics(value).strip()
    if value.startswith("? extends "):
        value = value[10:].strip()
    elif value.startswith("? super ") or value == "?":
        value = "Object"
    if value in PRIMITIVES:
        resolved = value
    elif value in variables:
        resolved = resolve_type(
            variables[value] or "Object", declaration, {}, known_types
        )
        resolved = resolved or "java.lang.Object"
    else:
        parts = value.replace("$", ".").split(".")
        head = parts[0]
        candidates = declaration["imports"].get(head, ())
        if len(candidates) == 1:
            resolved = ".".join((candidates[0], *parts[1:]))
        elif head in JAVA_LANG:
            resolved = ".".join((f"java.lang.{head}", *parts[1:]))
        elif head and head[0].islower() and len(parts) > 1:
            resolved = value
        else:
            candidates = set(known_types.get(head, ()))
            prefix = ".".join(
                item
                for item in (declaration["package"], declaration["top_level"])
                if item
            )
            candidates.update(
                item
                for item in known_types.get(head, ())
                if item == prefix or item.startswith(prefix + ".")
            )
            if len(candidates) != 1:
                return None
            resolved = ".".join((next(iter(candidates)), *parts[1:]))
    return resolved + "[]" * dimensions


def descriptor(value: str, varargs: bool = False) -> str:
    dimensions = 1 if varargs else 0
    while value.endswith("[]"):
        dimensions += 1
        value = value[:-2]
    atom = PRIMITIVES.get(value, f"L{value.replace('.', '/')};")
    return "[" * dimensions + atom


def collect_types(source: Source):
    rows = []

    def walk(node, names=(), inherited=()):
        if node.type not in TYPE_NODES:
            return
        name_node = node.child_by_field_name("name")
        current = names + (text(name_node, source.raw),)
        variables = inherited + type_variables(node, source.raw)
        rows.append((node, current, variables))
        body = next(
            (item for item in node.named_children if item.type in TYPE_BODIES),
            None,
        )
        if body is not None:
            for child in body.named_children:
                if child.type in TYPE_NODES:
                    walk(child, current, variables)

    for child in source.root.named_children:
        if child.type in TYPE_NODES:
            walk(child)
    return rows


def candidate_rows(sources: tuple[Source, ...]):
    types = [(source, *row) for source in sources for row in collect_types(source)]
    known: dict[str, set[str]] = {}
    for source, _node, names, _variables in types:
        full = ".".join(item for item in (source.package, *names) if item)
        known.setdefault(names[-1], set()).add(full)
        top = ".".join(item for item in (source.package, names[0]) if item)
        known.setdefault(names[0], set()).add(top)
    known_types = {key: tuple(sorted(values)) for key, values in known.items()}
    result = []
    for source, type_node, names, inherited in types:
        body = next(
            (item for item in type_node.named_children if item.type in TYPE_BODIES),
            None,
        )
        record_parameters = (
            parameter_parts(type_node.child_by_field_name("parameters"), source.raw)
            if type_node.type == "record_declaration"
            else ()
        )
        for node in body.named_children if body is not None else ():
            kind = METHOD_NODES.get(node.type)
            if kind is None:
                continue
            name_node = node.child_by_field_name("name")
            member_name = text(name_node, source.raw)
            parameters = (
                record_parameters
                if node.type == "compact_constructor_declaration"
                else parameter_parts(node.child_by_field_name("parameters"), source.raw)
            )
            if parameters is None:
                continue
            own_variables = inherited + type_variables(node, source.raw)
            type_node_value = node.child_by_field_name("type")
            return_type = (
                "void" if kind == "constructor" else text(type_node_value, source.raw)
            )
            declaration = {
                "package": source.package,
                "top_level": names[0],
                "imports": source.imports,
            }
            parameter_types = [
                resolve_type(value, declaration, dict(own_variables), known_types)
                for value, _varargs in parameters
            ]
            resolved_return = resolve_type(
                return_type, declaration, dict(own_variables), known_types
            )
            if (
                any(value is None for value in parameter_types)
                or resolved_return is None
            ):
                continue
            signature_name = "<init>" if kind == "constructor" else member_name
            signature = (
                f"{signature_name}({','.join(value for value, _ in parameters)}):"
                f"{return_type}"
            )
            signature = " ".join(signature.split()).replace(" ,", ",")
            erased = (
                f"{signature_name}("
                + "".join(
                    descriptor(value, parameters[index][1])
                    for index, value in enumerate(parameter_types)
                )
                + f"){descriptor(resolved_return)}"
            )
            start_line = node.start_point.row + 1
            end_line = max(
                start_line,
                node.end_point.row + (1 if node.end_point.column else 0),
            )
            result.append(
                {
                    "source_unit_id": source.path.name,
                    "document_bytes_hash": bytes_hash(source.raw),
                    "start_offset": node.start_byte,
                    "end_offset": node.end_byte,
                    "start_line": start_line,
                    "end_line": end_line,
                    "package_name": source.package,
                    "top_level_type_name": names[0],
                    "nested_type_path": list(names[1:]),
                    "member_kind": kind,
                    "member_name": member_name,
                    "canonical_source_signature": signature,
                    "erased_jvm_descriptor": erased,
                    "expected_supported": True,
                }
            )
    return sorted(
        result,
        key=lambda row: (
            row["source_unit_id"],
            row["start_offset"],
            row["member_name"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus", type=Path, default=Path("tests/fixtures/m341_java/corpus")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/m341_java/goldens/sealed_locations.json"),
    )
    parser.add_argument("--count", type=int, default=300)
    args = parser.parse_args()
    java_parser = Parser(Language(tree_sitter_java.language()))
    sources = []
    for path in sorted(args.corpus.rglob("*.java"), key=lambda item: item.name):
        raw = path.read_bytes()
        tree = java_parser.parse(raw, encoding="utf8")
        if tree.root_node.has_error:
            raise SystemExit(f"parse failure: {path}")
        sources.append(
            Source(
                path,
                raw,
                tree.root_node,
                package_name(tree.root_node, raw),
                imports(tree.root_node, raw),
            )
        )
    rows = candidate_rows(tuple(sources))[: args.count]
    if len(rows) < args.count:
        raise SystemExit(f"only {len(rows)} independently resolvable declarations")
    goldens = []
    for index, row in enumerate(rows, 1):
        body = {"golden_id": f"m341.golden.{index:04d}", **row}
        goldens.append({**body, "golden_hash": content_hash(body)})
    source_rows = sorted(
        (source.path.name, bytes_hash(source.raw)) for source in sources
    )
    body = {
        "schema_version": 1,
        "authoring_implementation": "m341.independent-tree-walk.v1",
        "sealed_before_proposals": True,
        "source_manifest_hash": content_hash(source_rows),
        "goldens": goldens,
        "positive_count": len(goldens),
    }
    output = {**body, "manifest_hash": content_hash(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(output) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"sealed {len(goldens)} goldens at {args.output}")


if __name__ == "__main__":
    main()
