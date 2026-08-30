"""Offline trust-bearing Java source indexing with pinned Tree-sitter grammar."""

from __future__ import annotations

import importlib.metadata
import re
from dataclasses import asdict, dataclass, replace

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.models import (
    SourceBundle,
    SourceDocument,
    SourceLocation,
    SourceMediaType,
)
from ai_brain.stage3.acquisition.sources import verify_bundle

TREE_SITTER_VERSION = "0.25.2"
TREE_SITTER_JAVA_VERSION = "0.23.5"
TREE_SITTER_JAVA_SOURCE_SHA256 = (
    "f5cd57b8f1270a7f0438878750d02ccc79421d45cca65ff284f1527e9ef02e38"
)
JAVA_PARSER_VERSION = (
    f"tree-sitter/{TREE_SITTER_VERSION}+tree-sitter-java/{TREE_SITTER_JAVA_VERSION}"
)
UNRESOLVED_DESCRIPTOR = "UNRESOLVED"

_TYPE_NODES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}
_TYPE_BODIES = {
    "class_body",
    "interface_body",
    "enum_body",
    "annotation_type_body",
}
_METHOD_NODES = {
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "compact_constructor_declaration": "constructor",
}
_PRIMITIVE_DESCRIPTORS = {
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
_JAVA_LANG = {
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
class JavaParameter:
    name: str
    source_type: str
    resolved_type: str | None
    type_span: SourceLocation
    name_span: SourceLocation
    varargs: bool
    parameter_hash: str


@dataclass(frozen=True)
class JavaDeclaration:
    node_id: str
    document_id: str
    source_snapshot_hash: str
    source_unit_id: str
    package_name: str | None
    imports: tuple[str, ...]
    wildcard_imports: tuple[str, ...]
    top_level_type_name: str
    nested_type_path: tuple[str, ...]
    local_type: bool
    member_kind: str
    member_name: str
    receiver_type: str
    canonical_source_signature: str | None
    erased_jvm_descriptor: str
    declaration_span: SourceLocation
    name_span: SourceLocation
    parameters: tuple[JavaParameter, ...]
    type_token_spans: tuple[SourceLocation, ...]
    javadoc_span: SourceLocation | None
    modifiers: tuple[str, ...]
    type_parameters: tuple[str, ...]
    type_variable_bounds: tuple[tuple[str, str], ...]
    return_type: str | None
    resolved_return_type: str | None
    declared_exceptions: tuple[str, ...]
    source_span_hash: str
    javadoc_span_hash: str | None
    parser_version: str
    grammar_artifact_sha256: str
    supported: bool
    unsupported_reason: str | None
    declaration_hash: str


@dataclass(frozen=True)
class JavaSourceIndex:
    parser_version: str
    grammar_version: str
    grammar_artifact_sha256: str
    source_execution: bool
    annotation_processing: bool
    document_manifest_hash: str
    declarations: tuple[JavaDeclaration, ...]
    declaration_count: int
    supported_declaration_count: int
    unsupported_declaration_count: int
    index_hash: str


@dataclass(frozen=True)
class _TypeContext:
    names: tuple[str, ...]
    local_type: bool
    type_variables: tuple[tuple[str, str], ...]
    record_parameters: tuple[tuple[str, str, SourceLocation, SourceLocation, bool], ...]


def bundle_requires_java_policy(bundle: SourceBundle) -> bool:
    """Use immutable document media type; domain tags never select policy."""

    return any(
        document.media_type is SourceMediaType.JAVA_SOURCE
        for document in bundle.documents
    )


def index_java_bundle(bundle: SourceBundle, store) -> JavaSourceIndex:
    verify_bundle(bundle, store=store)
    _verify_parser_installation()
    documents = tuple(
        document
        for document in bundle.documents
        if document.media_type is SourceMediaType.JAVA_SOURCE
    )
    if not documents:
        raise ValueError("Java source index requires JAVA_SOURCE documents")
    declarations = []
    for document in sorted(documents, key=lambda item: item.document_id):
        raw = store.get_blob(document.bytes_hash)
        declarations.extend(_index_document(document, raw))
    known_types = _known_types(tuple(declarations))
    resolved = tuple(_resolve_declaration(item, known_types) for item in declarations)
    ordered = tuple(
        sorted(
            resolved,
            key=lambda item: (
                item.source_unit_id,
                item.declaration_span.byte_start,
                item.node_id,
            ),
        )
    )
    document_rows = tuple(
        (item.document_id, item.document_hash, item.bytes_hash, item.relative_path)
        for item in sorted(documents, key=lambda value: value.document_id)
    )
    body = {
        "parser_version": JAVA_PARSER_VERSION,
        "grammar_version": TREE_SITTER_JAVA_VERSION,
        "grammar_artifact_sha256": TREE_SITTER_JAVA_SOURCE_SHA256,
        "source_execution": False,
        "annotation_processing": False,
        "document_manifest_hash": content_hash(document_rows),
        "declarations": ordered,
        "declaration_count": len(ordered),
        "supported_declaration_count": sum(item.supported for item in ordered),
        "unsupported_declaration_count": sum(not item.supported for item in ordered),
    }
    return JavaSourceIndex(**body, index_hash=content_hash(body))


def verify_java_source_index(
    index: JavaSourceIndex, bundle: SourceBundle, store
) -> None:
    rebuilt = index_java_bundle(bundle, store)
    if rebuilt != index:
        raise ValueError("Java source index does not match immutable source bytes")


def declaration_by_node_id(index: JavaSourceIndex) -> dict[str, JavaDeclaration]:
    return {item.node_id: item for item in index.declarations}


def _verify_parser_installation() -> None:
    if (
        importlib.metadata.version("tree-sitter") != TREE_SITTER_VERSION
        or importlib.metadata.version("tree-sitter-java") != TREE_SITTER_JAVA_VERSION
    ):
        raise RuntimeError("unpinned Java parser installation")
    language = Language(tree_sitter_java.language())
    if language.abi_version != 14:
        raise RuntimeError("unexpected tree-sitter-java grammar ABI")


def _index_document(
    document: SourceDocument, raw: bytes
) -> tuple[JavaDeclaration, ...]:
    if bytes_hash(raw) != document.bytes_hash:
        raise ValueError("Java source document hash mismatch")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Java source is not UTF-8") from error
    tree = Parser(Language(tree_sitter_java.language())).parse(raw, encoding="utf8")
    if tree.root_node.has_error:
        raise ValueError(f"Java grammar parse failure: {document.relative_path}")
    package = _package_name(tree.root_node, raw)
    imports, wildcard_imports = _imports(tree.root_node, raw)
    result: list[JavaDeclaration] = []

    def walk(node: Node, context: _TypeContext | None, in_executable: bool) -> None:
        if node.type in _TYPE_NODES:
            type_declaration, next_context = _type_declaration(
                node,
                context,
                in_executable,
                document,
                raw,
                package,
                imports,
                wildcard_imports,
            )
            result.append(type_declaration)
            body = _body_node(node)
            if body is not None:
                for child in body.named_children:
                    walk(child, next_context, False)
            return
        if context is not None and node.parent is not None:
            parent_type = node.parent.type
            if node.type in _METHOD_NODES and parent_type in _TYPE_BODIES:
                result.append(
                    _method_declaration(
                        node,
                        context,
                        document,
                        raw,
                        package,
                        imports,
                        wildcard_imports,
                    )
                )
                body = node.child_by_field_name("body")
                if body is not None:
                    for child in body.named_children:
                        walk(child, context, True)
                return
            if node.type == "field_declaration" and parent_type in _TYPE_BODIES:
                result.extend(
                    _field_declarations(
                        node,
                        context,
                        document,
                        raw,
                        package,
                        imports,
                        wildcard_imports,
                    )
                )
                return
            if node.type == "enum_constant" and parent_type == "enum_body":
                result.append(
                    _enum_constant(
                        node,
                        context,
                        document,
                        raw,
                        package,
                        imports,
                        wildcard_imports,
                    )
                )
                return
        for child in node.named_children:
            walk(child, context, in_executable or node.type in _METHOD_NODES)

    for child in tree.root_node.named_children:
        walk(child, None, False)
    return tuple(result)


def _type_declaration(
    node,
    context,
    in_executable,
    document,
    raw,
    package,
    imports,
    wildcard_imports,
):
    name_node = _required_field(node, "name")
    name = _text(name_node, raw)
    names = (name,) if context is None else context.names + (name,)
    local = in_executable or (context.local_type if context else False)
    own_type_variables = _type_variables(node, raw)
    inherited = context.type_variables if context else ()
    type_variables = inherited + own_type_variables
    record_parameters = (
        _parameter_parts(node.child_by_field_name("parameters"), raw)
        if node.type == "record_declaration"
        else ()
    )
    receiver = _receiver(package, names)
    declaration = _make_declaration(
        node=node,
        name_node=name_node,
        document=document,
        raw=raw,
        package=package,
        imports=imports,
        wildcard_imports=wildcard_imports,
        names=names,
        local_type=local,
        member_kind=_TYPE_NODES[node.type],
        member_name=name,
        receiver_type=receiver,
        canonical_source_signature=None,
        parameters=(),
        type_variables=type_variables,
        return_type=None,
        declared_exceptions=(),
        supported=not local,
        unsupported_reason="local_type" if local else None,
    )
    return declaration, _TypeContext(names, local, type_variables, record_parameters)


def _method_declaration(
    node, context, document, raw, package, imports, wildcard_imports
):
    name_node = _required_field(node, "name")
    name = _text(name_node, raw)
    kind = _METHOD_NODES[node.type]
    parameters = (
        context.record_parameters
        if node.type == "compact_constructor_declaration"
        else _parameter_parts(node.child_by_field_name("parameters"), raw)
    )
    own_type_variables = _type_variables(node, raw)
    type_variables = context.type_variables + own_type_variables
    type_node = node.child_by_field_name("type")
    return_type = None if kind == "constructor" else _text(type_node, raw)
    exceptions = _throws(node, raw)
    signature_name = "<init>" if kind == "constructor" else name
    signature = (
        f"{signature_name}({','.join(item[1] for item in parameters)})"
        f":{'void' if kind == 'constructor' else return_type}"
    )
    local = context.local_type
    return _make_declaration(
        node=node,
        name_node=name_node,
        document=document,
        raw=raw,
        package=package,
        imports=imports,
        wildcard_imports=wildcard_imports,
        names=context.names,
        local_type=local,
        member_kind=kind,
        member_name=name,
        receiver_type=_receiver(package, context.names),
        canonical_source_signature=_normalize_source_signature(signature),
        parameters=parameters,
        type_variables=type_variables,
        return_type="void" if kind == "constructor" else return_type,
        declared_exceptions=exceptions,
        supported=not local,
        unsupported_reason="local_type_member" if local else None,
    )


def _field_declarations(
    node, context, document, raw, package, imports, wildcard_imports
):
    type_node = node.child_by_field_name("type")
    source_type = _text(type_node, raw)
    result = []
    for declarator in (
        child for child in node.named_children if child.type == "variable_declarator"
    ):
        name_node = _required_field(declarator, "name")
        name = _text(name_node, raw)
        result.append(
            _make_declaration(
                node=node,
                name_node=name_node,
                document=document,
                raw=raw,
                package=package,
                imports=imports,
                wildcard_imports=wildcard_imports,
                names=context.names,
                local_type=context.local_type,
                member_kind="field",
                member_name=name,
                receiver_type=_receiver(package, context.names),
                canonical_source_signature=f"{name}:{source_type}",
                parameters=(),
                type_variables=context.type_variables,
                return_type=source_type,
                declared_exceptions=(),
                supported=not context.local_type,
                unsupported_reason=(
                    "local_type_member" if context.local_type else None
                ),
            )
        )
    return tuple(result)


def _enum_constant(node, context, document, raw, package, imports, wildcard_imports):
    name_node = node.named_children[0]
    name = _text(name_node, raw)
    return _make_declaration(
        node=node,
        name_node=name_node,
        document=document,
        raw=raw,
        package=package,
        imports=imports,
        wildcard_imports=wildcard_imports,
        names=context.names,
        local_type=context.local_type,
        member_kind="constant",
        member_name=name,
        receiver_type=_receiver(package, context.names),
        canonical_source_signature=f"{name}:{_receiver(package, context.names)}",
        parameters=(),
        type_variables=context.type_variables,
        return_type=_receiver(package, context.names),
        declared_exceptions=(),
        supported=not context.local_type,
        unsupported_reason="local_type_member" if context.local_type else None,
    )


def _make_declaration(
    *,
    node,
    name_node,
    document,
    raw,
    package,
    imports,
    wildcard_imports,
    names,
    local_type,
    member_kind,
    member_name,
    receiver_type,
    canonical_source_signature,
    parameters,
    type_variables,
    return_type,
    declared_exceptions,
    supported,
    unsupported_reason,
):
    declaration_span = _location(node)
    javadoc_node = _associated_javadoc(node)
    parameter_rows = tuple(
        JavaParameter(
            name=item[0],
            source_type=item[1],
            resolved_type=None,
            type_span=item[2],
            name_span=item[3],
            varargs=item[4],
            parameter_hash="",
        )
        for item in parameters
    )
    parameter_rows = tuple(
        replace(
            item,
            parameter_hash=content_hash(
                {
                    key: value
                    for key, value in asdict(item).items()
                    if key != "parameter_hash"
                }
            ),
        )
        for item in parameter_rows
    )
    type_spans = tuple(item.type_span for item in parameter_rows)
    type_node = node.child_by_field_name("type")
    if type_node is not None:
        type_spans += (_location(type_node),)
    modifiers = _modifiers(node, raw)
    type_parameter_names = tuple(item[0] for item in type_variables)
    body = {
        "node_id": "",
        "document_id": document.document_id,
        "source_snapshot_hash": document.bytes_hash,
        "source_unit_id": document.relative_path.replace("\\", "/"),
        "package_name": package,
        "imports": imports,
        "wildcard_imports": wildcard_imports,
        "top_level_type_name": names[0],
        "nested_type_path": names[1:],
        "local_type": local_type,
        "member_kind": member_kind,
        "member_name": member_name,
        "receiver_type": receiver_type,
        "canonical_source_signature": canonical_source_signature,
        "erased_jvm_descriptor": UNRESOLVED_DESCRIPTOR,
        "declaration_span": declaration_span,
        "name_span": _location(name_node),
        "parameters": parameter_rows,
        "type_token_spans": type_spans,
        "javadoc_span": _location(javadoc_node) if javadoc_node else None,
        "modifiers": modifiers,
        "type_parameters": type_parameter_names,
        "type_variable_bounds": type_variables,
        "return_type": return_type,
        "resolved_return_type": None,
        "declared_exceptions": declared_exceptions,
        "source_span_hash": bytes_hash(raw[node.start_byte : node.end_byte]),
        "javadoc_span_hash": (
            bytes_hash(raw[javadoc_node.start_byte : javadoc_node.end_byte])
            if javadoc_node
            else None
        ),
        "parser_version": JAVA_PARSER_VERSION,
        "grammar_artifact_sha256": TREE_SITTER_JAVA_SOURCE_SHA256,
        "supported": supported,
        "unsupported_reason": unsupported_reason,
    }
    node_key = {
        "document": body["document_id"],
        "snapshot": body["source_snapshot_hash"],
        "start": declaration_span.byte_start,
        "end": declaration_span.byte_end,
        "kind": member_kind,
        "name": member_name,
    }
    body["node_id"] = f"java-node.{content_hash(node_key)[:32]}"
    return JavaDeclaration(**body, declaration_hash=content_hash(body))


def _resolve_declaration(
    declaration: JavaDeclaration, known_types: dict[str, tuple[str, ...]]
) -> JavaDeclaration:
    imports = _explicit_import_map(declaration.imports)
    variables = dict(declaration.type_variable_bounds)
    parameters = []
    unresolved = declaration.unsupported_reason
    for parameter in declaration.parameters:
        resolved = _resolve_type(
            parameter.source_type,
            declaration,
            imports,
            variables,
            known_types,
        )
        if resolved is None:
            unresolved = (
                unresolved or f"unresolved_parameter_type:{parameter.source_type}"
            )
        provisional = replace(parameter, resolved_type=resolved, parameter_hash="")
        row = asdict(provisional)
        row.pop("parameter_hash")
        parameters.append(replace(provisional, parameter_hash=content_hash(row)))
    resolved_return = (
        _resolve_type(
            declaration.return_type,
            declaration,
            imports,
            variables,
            known_types,
        )
        if declaration.return_type
        else None
    )
    if declaration.member_kind in {"method", "constructor"}:
        if declaration.return_type and resolved_return is None:
            unresolved = (
                unresolved or f"unresolved_return_type:{declaration.return_type}"
            )
        parameter_descriptors = tuple(
            _descriptor(item.resolved_type, item.varargs) for item in parameters
        )
        return_descriptor = _descriptor(resolved_return, False, allow_void=True)
        descriptor = (
            UNRESOLVED_DESCRIPTOR
            if None in parameter_descriptors or return_descriptor is None
            else (
                f"{'<init>' if declaration.member_kind == 'constructor' else declaration.member_name}"
                f"({''.join(parameter_descriptors)}){return_descriptor}"
            )
        )
    else:
        descriptor = UNRESOLVED_DESCRIPTOR
    supported = declaration.supported and unresolved is None
    provisional = replace(
        declaration,
        parameters=tuple(parameters),
        resolved_return_type=resolved_return,
        erased_jvm_descriptor=descriptor,
        supported=supported,
        unsupported_reason=unresolved,
        declaration_hash="",
    )
    row = asdict(provisional)
    row.pop("declaration_hash")
    return replace(provisional, declaration_hash=content_hash(row))


def _resolve_type(value, declaration, imports, variables, known_types):
    if value is None:
        return None
    text = _clean_type(value)
    dimensions = 0
    if text.endswith("..."):
        dimensions += 1
        text = text[:-3]
    while text.endswith("[]"):
        dimensions += 1
        text = text[:-2]
    text = _erase_generics(text).strip()
    if text.startswith("? extends "):
        text = text[10:].strip()
    elif text.startswith("? super ") or text == "?":
        text = "Object"
    if text in _PRIMITIVE_DESCRIPTORS:
        resolved = text
    elif text in variables:
        bound = variables[text] or "Object"
        resolved = (
            _resolve_type(bound, declaration, imports, {}, known_types)
            or "java.lang.Object"
        )
    else:
        parts = text.replace("$", ".").split(".")
        head = parts[0]
        if head in imports:
            candidates = imports[head]
            if len(candidates) != 1:
                return None
            resolved = ".".join((candidates[0], *parts[1:]))
        elif head in _JAVA_LANG:
            resolved = ".".join((f"java.lang.{head}", *parts[1:]))
        elif head and head[0].islower() and len(parts) > 1:
            resolved = text
        else:
            candidates = set(known_types.get(head, ()))
            current_prefix = ".".join(
                item
                for item in (declaration.package_name, declaration.top_level_type_name)
                if item
            )
            candidates.update(
                item
                for item in known_types.get(head, ())
                if item == current_prefix or item.startswith(current_prefix + ".")
            )
            if len(candidates) != 1:
                return None
            resolved = ".".join((next(iter(candidates)), *parts[1:]))
    return resolved + "[]" * dimensions


def _descriptor(value: str | None, varargs: bool, *, allow_void=False):
    if value is None:
        return None
    text = value
    dimensions = 1 if varargs else 0
    while text.endswith("[]"):
        dimensions += 1
        text = text[:-2]
    if text == "void" and not allow_void:
        return None
    descriptor = _PRIMITIVE_DESCRIPTORS.get(text)
    if descriptor is None:
        descriptor = f"L{text.replace('.', '/')};"
    return "[" * dimensions + descriptor


def _known_types(declarations):
    values: dict[str, set[str]] = {}
    for item in declarations:
        if item.member_kind not in {
            "class",
            "interface",
            "enum",
            "record",
            "annotation",
        }:
            continue
        full = item.receiver_type
        values.setdefault(item.member_name, set()).add(full)
        values.setdefault(item.top_level_type_name, set()).add(
            _receiver(item.package_name, (item.top_level_type_name,))
        )
    return {key: tuple(sorted(value)) for key, value in values.items()}


def _package_name(root, raw):
    node = next(
        (item for item in root.named_children if item.type == "package_declaration"),
        None,
    )
    if node is None:
        return None
    named = node.named_children[0]
    return _text(named, raw)


def _imports(root, raw):
    explicit = []
    wildcard = []
    for node in root.named_children:
        if node.type != "import_declaration":
            continue
        value = (
            _text(node, raw)
            .removeprefix("import ")
            .removeprefix("static ")
            .rstrip(";")
            .strip()
        )
        (wildcard if value.endswith(".*") else explicit).append(
            value.removesuffix(".*")
        )
    return tuple(sorted(explicit)), tuple(sorted(wildcard))


def _explicit_import_map(values):
    result: dict[str, list[str]] = {}
    for value in values:
        result.setdefault(value.rsplit(".", 1)[-1], []).append(value)
    return {key: tuple(sorted(items)) for key, items in result.items()}


def _type_variables(node, raw):
    container = next(
        (item for item in node.named_children if item.type == "type_parameters"), None
    )
    if container is None:
        return ()
    result = []
    for parameter in container.named_children:
        if parameter.type != "type_parameter":
            continue
        name = _text(parameter.named_children[0], raw)
        bound_node = next(
            (item for item in parameter.named_children if item.type == "type_bound"),
            None,
        )
        bound = (
            _text(bound_node.named_children[0], raw)
            if bound_node and bound_node.named_children
            else "Object"
        )
        result.append((name, bound))
    return tuple(result)


def _parameter_parts(container, raw):
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
        if name_node is None:
            name_node = next(
                (
                    item
                    for item in reversed(parameter.named_children)
                    if item.type == "identifier"
                ),
                None,
            )
        if type_node is None:
            excluded = {name_node.id} if name_node else set()
            type_node = next(
                (
                    item
                    for item in parameter.named_children
                    if item.id not in excluded
                    and item.type not in {"modifiers", "variable_declarator"}
                ),
                None,
            )
        if name_node is None or type_node is None:
            raise ValueError("Java grammar parameter lacks typed name")
        result.append(
            (
                _text(name_node, raw),
                _text(type_node, raw) + ("..." if varargs else ""),
                _location(type_node),
                _location(name_node),
                varargs,
            )
        )
    return tuple(result)


def _throws(node, raw):
    container = next(
        (item for item in node.named_children if item.type == "throws"), None
    )
    if container is None:
        return ()
    return tuple(
        _text(item, raw)
        for item in container.named_children
        if item.type not in {"throws"}
    )


def _modifiers(node, raw):
    container = next(
        (item for item in node.named_children if item.type == "modifiers"), None
    )
    if container is None:
        return ()
    return tuple(
        value for value in _text(container, raw).split() if not value.startswith("@")
    )


def _associated_javadoc(node):
    sibling = node.prev_named_sibling
    if sibling is not None and sibling.type == "block_comment":
        return sibling
    return None


def _body_node(node):
    body = node.child_by_field_name("body")
    if body is not None:
        return body
    return next(
        (item for item in node.named_children if item.type in _TYPE_BODIES), None
    )


def _required_field(node, field):
    value = node.child_by_field_name(field)
    if value is None:
        raise ValueError(f"Java grammar node lacks {field}: {node.type}")
    return value


def _receiver(package, names):
    return ".".join(item for item in (package, *names) if item)


def _text(node, raw):
    if node is None:
        return None
    return raw[node.start_byte : node.end_byte].decode("utf-8", errors="strict")


def _location(node):
    start_line = node.start_point.row + 1
    end_line = max(start_line, node.end_point.row + (1 if node.end_point.column else 0))
    return SourceLocation(
        node.start_byte,
        node.end_byte,
        start_line,
        end_line,
        (),
    )


def _clean_type(value):
    text = re.sub(r"@[\w.]+(?:\s*\([^)]*\))?\s*", "", value)
    return " ".join(text.split()).replace(" []", "[]")


def _erase_generics(value):
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


def _normalize_source_signature(value):
    return " ".join(value.split()).replace(" ,", ",")
