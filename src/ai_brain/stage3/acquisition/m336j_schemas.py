"""Real strict versioned request/response codecs for the M-33.6j route."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

_SHA256 = r"[0-9a-f]{64}"
_GIT_SHA = r"[0-9a-f]{40}"


@dataclass(frozen=True)
class M336JSchemaField:
    name: str
    value_type: str
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    minimum_length: int | None = None
    maximum_length: int | None = None
    pattern: str | None = None
    enum: tuple[str, ...] = ()
    item_type: str | None = None
    maximum_items: int | None = None
    nested_fields: tuple[M336JSchemaField, ...] = ()
    nested_additional_fields_forbidden: bool = True


@dataclass(frozen=True)
class M336JStrictSchema:
    schema_id: str
    schema_version: int
    direction: str
    operation: str
    fields: tuple[M336JSchemaField, ...]
    additional_fields_forbidden: bool
    canonical_ordering: str
    maximum_serialized_bytes: int
    schema_hash: str


@dataclass(frozen=True)
class M336JStrictCodec:
    schema: M336JStrictSchema

    def serialize(self, value: dict[str, Any]) -> bytes:
        self.validate(value)
        raw = canonical_json(value).encode("utf-8")
        if len(raw) > self.schema.maximum_serialized_bytes:
            raise ValueError("M336J schema serialization exceeds its byte bound")
        return raw

    def deserialize(self, raw: bytes) -> dict[str, Any]:
        if len(raw) > self.schema.maximum_serialized_bytes:
            raise ValueError("M336J schema input exceeds its byte bound")
        try:
            value = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("M336J schema input is not strict JSON") from error
        if not isinstance(value, dict):
            raise TypeError("M336J schema root must be an object")
        self.validate(value)
        if self.serialize(value) != raw:
            raise ValueError("M336J schema input is not canonical")
        return value

    def validate(self, value: dict[str, Any]) -> None:
        verify_schema(self.schema)
        _validate_object(
            value,
            self.schema.fields,
            additional_forbidden=self.schema.additional_fields_forbidden,
        )


@dataclass(frozen=True)
class M336JPublicSchemaRegistry:
    schema_version: int
    contract_role: str
    schemas: tuple[M336JStrictSchema, ...]
    schema_count: int
    unresolved_schema_count: int
    synthetic_tuple_schema_hash_count: int
    incompatible_route_schema_edge_count: int
    status: str
    registry_hash: str


def _f(name: str, value_type: str, **values: Any) -> M336JSchemaField:
    return M336JSchemaField(name=name, value_type=value_type, **values)


def _hash(name: str, *, required: bool = True) -> M336JSchemaField:
    return _f(name, "string", required=required, pattern=_SHA256, maximum_length=64)


def _sha(name: str) -> M336JSchemaField:
    return _f(name, "string", pattern=_GIT_SHA, maximum_length=40)


def _text(name: str, *, maximum: int = 4096, required: bool = True) -> M336JSchemaField:
    return _f(
        name, "string", required=required, minimum_length=1, maximum_length=maximum
    )


def _integer(name: str, *, maximum: int = 2**63 - 1) -> M336JSchemaField:
    return _f(name, "integer", minimum=0, maximum=maximum)


_REQUEST_COMMON = (
    _f("schema_version", "integer", minimum=1, maximum=1),
    _text("route_run_id", maximum=128),
    _sha("exact_sha"),
    _hash("component_binding_hash"),
    _hash("request_hash"),
)
_RESPONSE_COMMON = (
    _f("schema_version", "integer", minimum=1, maximum=1),
    _text("contract_role", maximum=128),
    _text("route_run_id", maximum=128),
    _sha("exact_sha"),
    _hash("request_hash"),
    _hash("component_binding_hash"),
    _hash("host_identity_hash"),
    _f("status", "string", enum=("PASS", "FAIL")),
    _hash("receipt_hash"),
)


def _schema(
    operation: str,
    direction: str,
    extras: tuple[M336JSchemaField, ...],
    *,
    maximum_bytes: int = 4 * 1024 * 1024,
) -> M336JStrictSchema:
    fields = (_REQUEST_COMMON if direction == "request" else _RESPONSE_COMMON) + extras
    body = {
        "schema_id": f"m336j.{operation}.{direction}.v1",
        "schema_version": 1,
        "direction": direction.upper(),
        "operation": operation,
        "fields": fields,
        "additional_fields_forbidden": True,
        "canonical_ordering": "UTF8_CODEPOINT_SORTED_OBJECT_KEYS_DECLARED_ARRAY_ORDER",
        "maximum_serialized_bytes": maximum_bytes,
    }
    return M336JStrictSchema(**body, schema_hash=content_hash(body))


def _request_response_schemas() -> tuple[M336JStrictSchema, ...]:
    operations = {
        "execution-capsule-verification": (
            (_text("private_capsule_handle"),),
            (
                _hash("capsule_receipt_hash"),
                _f(
                    "python_environment",
                    "object",
                    nested_fields=(
                        _hash("environment_manifest_hash"),
                        _hash("package_manifest_hash"),
                        _f("package_count", "integer", minimum=1, maximum=100_000),
                        _f("user_site_loading_disabled", "boolean"),
                        _f("torch_imported", "boolean"),
                    ),
                ),
                _hash("dependency_manifest_hash"),
            ),
        ),
        "host-preflight": (
            (_hash("capsule_receipt_hash"), _hash("dependency_manifest_hash")),
            (
                _hash("capsule_receipt_hash"),
                _hash("dependency_manifest_hash"),
                _integer("bare_executable_lookup_count", maximum=0),
                _integer("profile_startup_dependency_count", maximum=0),
                _integer("network_access_count", maximum=0),
            ),
        ),
        "storage-capacity": (
            (_hash("storage_plan_hash"), _integer("required_free_bytes")),
            (
                _hash("storage_plan_hash"),
                _integer("required_free_bytes"),
                _integer("available_free_bytes"),
                _integer("available_free_inodes"),
                _hash("filesystem_identity_hash"),
                _f("writable", "boolean"),
                _f("atomic_rename", "boolean"),
                _f("fsync", "boolean"),
            ),
        ),
        "tree-upload": (
            (
                _text("relative_destination"),
                _hash("archive_hash"),
                _integer("archive_size"),
                _integer("file_count", maximum=100_000),
                _hash("portable_tree_hash"),
                _hash("transfer_limit_hash"),
            ),
            (
                _hash("archive_hash"),
                _integer("archive_size"),
                _integer("file_count", maximum=100_000),
                _hash("portable_tree_hash"),
                _hash("transfer_limit_hash"),
            ),
        ),
        "tree-download": (
            (_text("relative_source"), _hash("transfer_limit_hash")),
            (
                _hash("archive_hash"),
                _integer("archive_size"),
                _integer("file_count", maximum=100_000),
                _hash("portable_tree_hash"),
                _hash("transfer_limit_hash"),
            ),
        ),
        "source-materialization": (
            (
                _hash("selected_manifest_hash"),
                _hash("binding_manifest_hash"),
                _hash("vault_tree_hash"),
            ),
            (
                _hash("selected_manifest_hash"),
                _hash("binding_manifest_hash"),
                _hash("snapshot_tree_hash"),
                _integer("file_count", maximum=100_000),
            ),
        ),
        "compiler-aware-production": (
            (
                _hash("materialization_receipt_hash"),
                _hash("selected_manifest_hash"),
                _hash("binding_manifest_hash"),
            ),
            (
                _hash("selected_manifest_hash"),
                _hash("binding_manifest_hash"),
                _hash("candidate_pack_hash"),
                _hash("production_seal_hash"),
            ),
        ),
        "replay": (
            (_hash("production_seal_hash"), _hash("candidate_pack_hash")),
            (_hash("candidate_pack_hash"), _hash("replay_receipt_hash")),
        ),
        "independent-evaluation": (
            (
                _hash("windows_production_seal_hash"),
                _hash("karina_production_seal_hash"),
                _hash("candidate_pack_hash"),
            ),
            (
                _hash("candidate_pack_hash"),
                _hash("evaluation_receipt_hash"),
                _integer("platform_neutral_difference_count", maximum=0),
            ),
        ),
        "installed-runtime": (
            (_hash("candidate_pack_hash"),),
            (
                _hash("candidate_pack_hash"),
                _hash("runtime_receipt_hash"),
                _integer("source_input_count", maximum=0),
            ),
        ),
        "response-verification": (
            (_hash("response_hash"), _hash("response_schema_hash")),
            (
                _hash("response_hash"),
                _hash("response_schema_hash"),
                _hash("verified_receipt_hash"),
            ),
        ),
    }
    schemas = []
    for operation, (request, response) in operations.items():
        schemas.append(_schema(operation, "request", request))
        schemas.append(_schema(operation, "response", response))
    return tuple(schemas)


M336J_SCHEMAS = _request_response_schemas()
M336J_SCHEMA_BY_ID = {schema.schema_id: schema for schema in M336J_SCHEMAS}
M336J_SCHEMA_PAIRS = {
    operation: (
        M336J_SCHEMA_BY_ID[f"m336j.{operation}.request.v1"],
        M336J_SCHEMA_BY_ID[f"m336j.{operation}.response.v1"],
    )
    for operation in {schema.operation for schema in M336J_SCHEMAS}
}

M336J_ROUTE_ROLE_SCHEMA_OPERATION = {
    "REMOTE_EXECUTION_CAPSULE_VERIFIER": "execution-capsule-verification",
    "REMOTE_COMMAND_PLAN_BUILDER": "response-verification",
    "REMOTE_HOST_PREFLIGHT": "host-preflight",
    "REMOTE_STORAGE_PREFLIGHT": "storage-capacity",
    "REMOTE_TREE_UPLOAD": "tree-upload",
    "REMOTE_TREE_DOWNLOAD": "tree-download",
    "REMOTE_SELECTED_SOURCE_MATERIALIZER": "source-materialization",
    "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER": "compiler-aware-production",
    "REMOTE_REPLAY_AND_PACK_VERIFIER": "replay",
    "REMOTE_INDEPENDENT_EVALUATOR": "independent-evaluation",
    "REMOTE_INSTALLED_RUNTIME": "installed-runtime",
    "REMOTE_RESPONSE_VERIFIER": "response-verification",
}


def build_public_schema_registry() -> M336JPublicSchemaRegistry:
    validate_schema_registry()
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_STRICT_SCHEMA_REGISTRY",
        "schemas": M336J_SCHEMAS,
        "schema_count": len(M336J_SCHEMAS),
        "unresolved_schema_count": 0,
        "synthetic_tuple_schema_hash_count": 0,
        "incompatible_route_schema_edge_count": 0,
        "status": "PASS",
    }
    return M336JPublicSchemaRegistry(**body, registry_hash=content_hash(body))


def schema_pair_for_route_role(
    route_role: str,
) -> tuple[M336JStrictSchema, M336JStrictSchema]:
    try:
        return M336J_SCHEMA_PAIRS[M336J_ROUTE_ROLE_SCHEMA_OPERATION[route_role]]
    except KeyError as error:
        raise ValueError("M336J route role has no real schema pair") from error


def strict_codec(schema_id: str) -> M336JStrictCodec:
    try:
        schema = M336J_SCHEMA_BY_ID[schema_id]
    except KeyError as error:
        raise ValueError("M336J schema is unresolved") from error
    verify_schema(schema)
    return M336JStrictCodec(schema)


def verify_schema(schema: M336JStrictSchema) -> None:
    body = asdict(schema)
    claimed = body.pop("schema_hash")
    if (
        schema.schema_version != 1
        or schema.direction not in {"REQUEST", "RESPONSE"}
        or not schema.additional_fields_forbidden
        or schema.canonical_ordering
        != "UTF8_CODEPOINT_SORTED_OBJECT_KEYS_DECLARED_ARRAY_ORDER"
        or schema.maximum_serialized_bytes <= 0
        or content_hash(body) != claimed
        or len({field.name for field in schema.fields}) != len(schema.fields)
    ):
        raise ValueError("M336J strict schema is not content-derived")


def validate_schema_registry() -> None:
    identifiers = tuple(schema.schema_id for schema in M336J_SCHEMAS)
    if len(identifiers) != len(set(identifiers)) or len(M336J_SCHEMAS) != 22:
        raise ValueError("M336J strict schema registry is incomplete")
    for schema in M336J_SCHEMAS:
        verify_schema(schema)


def roundtrip_strict_object(schema_id: str, value: dict[str, Any]) -> bytes:
    codec = strict_codec(schema_id)
    first = codec.serialize(value)
    typed = codec.deserialize(first)
    second = codec.serialize(typed)
    if first != second:
        raise ValueError("M336J typed schema roundtrip is not byte-identical")
    return second


def _validate_object(
    value: dict[str, Any],
    fields: tuple[M336JSchemaField, ...],
    *,
    additional_forbidden: bool,
) -> None:
    if not isinstance(value, dict):
        raise TypeError("M336J schema value must be an object")
    allowed = {field.name for field in fields}
    required = {field.name for field in fields if field.required}
    if required - set(value) or (additional_forbidden and set(value) - allowed):
        raise ValueError("M336J schema object fields differ")
    by_name = {field.name: field for field in fields}
    for name, item in value.items():
        _validate_field(item, by_name[name])


def _validate_field(value: Any, field: M336JSchemaField) -> None:
    types = {
        "string": str,
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
        "null": type(None),
    }
    expected = types[field.value_type]
    if not isinstance(value, expected) or (
        field.value_type == "integer" and isinstance(value, bool)
    ):
        raise TypeError(f"M336J schema field {field.name} has wrong type")
    if isinstance(value, str):
        if field.minimum_length is not None and len(value) < field.minimum_length:
            raise ValueError(f"M336J schema field {field.name} is too short")
        if field.maximum_length is not None and len(value) > field.maximum_length:
            raise ValueError(f"M336J schema field {field.name} is too long")
        if field.pattern is not None and re.fullmatch(field.pattern, value) is None:
            raise ValueError(f"M336J schema field {field.name} has invalid syntax")
        if field.enum and value not in field.enum:
            raise ValueError(f"M336J schema field {field.name} has invalid enum")
    if isinstance(value, int) and not isinstance(value, bool):
        if field.minimum is not None and value < field.minimum:
            raise ValueError(f"M336J schema field {field.name} is below minimum")
        if field.maximum is not None and value > field.maximum:
            raise ValueError(f"M336J schema field {field.name} exceeds maximum")
    if isinstance(value, dict):
        _validate_object(
            value,
            field.nested_fields,
            additional_forbidden=field.nested_additional_fields_forbidden,
        )
    if isinstance(value, list):
        if field.maximum_items is not None and len(value) > field.maximum_items:
            raise ValueError(f"M336J schema field {field.name} has too many items")
        if field.item_type is not None:
            item_field = M336JSchemaField(field.name, field.item_type)
            for item in value:
                _validate_field(item, item_field)


validate_schema_registry()
