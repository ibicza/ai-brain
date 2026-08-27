"""Checksummed registry and explicit implementation manifests for local tools."""

from __future__ import annotations

import inspect
import platform
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.router import tools as tool_module
from ai_brain.stage2.router.models import (
    ToolApprovalPolicy,
    ToolArgumentValidation,
    ToolArgumentValidationStatus,
    ToolDescriptor,
    ToolExecutionClass,
    ToolImplementationManifest,
)
from ai_brain.stage2.router.tools import ToolInputError
from ai_brain.stage2.router.version import (
    TOOL_IMPLEMENTATION_POLICY_VERSION,
    TOOL_REGISTRY_SCHEMA_VERSION,
)

ToolImplementation = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistryIntegrityError(ValueError):
    pass


class ToolImplementationStaleError(ToolRegistryIntegrityError):
    pass


_MANIFEST_DEPENDENCIES = {
    "decimal_arithmetic": {
        "helpers": (
            "validate_decimal_arguments",
            "_decimal",
            "_validate_decimal_tuple",
            "_estimated_fixed_length",
            "_render_decimal",
        ),
        "constants": (
            "_DECIMAL_RE.pattern",
            "_DECIMAL_RE.flags",
            "DECIMAL_TOOL_LIMITS",
            "MAX_OPERANDS",
            "MAX_DECIMAL_DIGITS",
            "DECIMAL_INPUT_NORMALIZATION_POLICY",
            "DECIMAL_CONTEXT_POLICY",
            "DECIMAL_RENDERING_POLICY",
        ),
        "input_policy": tool_module.DECIMAL_INPUT_NORMALIZATION_POLICY,
        "numeric_policy": tool_module.DECIMAL_CONTEXT_POLICY,
        "output_policy": tool_module.DECIMAL_RENDERING_POLICY,
    },
    "date_difference": {
        "helpers": ("validate_date_arguments",),
        "constants": (
            "DATE_PARSING_POLICY",
            "DATE_ALLOWED_MODES",
            "DATE_OUTPUT_POLICY",
        ),
        "input_policy": tool_module.DATE_PARSING_POLICY,
        "numeric_policy": "calendar-date-v1",
        "output_policy": tool_module.DATE_OUTPUT_POLICY,
    },
}


def build_tool_implementation_manifest(
    tool_id: str,
    implementation: ToolImplementation | None = None,
    *,
    source_overrides: dict[str, str] | None = None,
    constant_overrides: dict[str, Any] | None = None,
) -> ToolImplementationManifest:
    if tool_id not in _MANIFEST_DEPENDENCIES:
        raise KeyError(f"unknown manifest policy: {tool_id}")
    implementation = implementation or getattr(tool_module, tool_id)
    policy = _MANIFEST_DEPENDENCIES[tool_id]
    source_overrides = source_overrides or {}
    constant_overrides = constant_overrides or {}
    entry_source = source_overrides.get(
        implementation.__qualname__, inspect.getsource(implementation)
    )
    helper_hashes = tuple(
        (
            name,
            content_hash(
                source_overrides.get(
                    name, inspect.getsource(getattr(tool_module, name))
                )
            ),
        )
        for name in policy["helpers"]
    )
    constant_hashes = tuple(
        (name, content_hash(_manifest_constant(name, constant_overrides)))
        for name in policy["constants"]
    )
    body = {
        "tool_id": tool_id,
        "tool_version": 2,
        "module": implementation.__module__,
        "entry_function_qualified_name": implementation.__qualname__,
        "entry_function_source_hash": content_hash(entry_source),
        "helper_function_source_hashes": helper_hashes,
        "constant_value_hashes": constant_hashes,
        "input_normalization_policy": str(policy["input_policy"]),
        "numeric_context_policy": str(policy["numeric_policy"]),
        "output_canonicalization_policy": str(policy["output_policy"]),
        "runtime_contract": f"CPython>={platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}",
        "implementation_policy_version": TOOL_IMPLEMENTATION_POLICY_VERSION,
    }
    return ToolImplementationManifest(**body, manifest_hash=content_hash(body))


def _manifest_constant(name: str, overrides: dict[str, Any]) -> Any:
    if name in overrides:
        return overrides[name]
    if name == "_DECIMAL_RE.pattern":
        return tool_module._DECIMAL_RE.pattern
    if name == "_DECIMAL_RE.flags":
        return tool_module._DECIMAL_RE.flags
    return getattr(tool_module, name)


class ToolRegistry:
    def __init__(
        self,
        descriptors: dict[str, ToolDescriptor],
        implementations: dict[str, ToolImplementation],
        manifests: dict[str, ToolImplementationManifest],
    ) -> None:
        self.descriptors = dict(descriptors)
        self._implementations = dict(implementations)
        self.manifests = dict(manifests)
        self.verify()
        self.registry_hash = content_hash(
            {
                "schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
                "descriptors": tuple(
                    asdict(self.descriptors[key]) for key in sorted(self.descriptors)
                ),
                "manifest_hashes": tuple(
                    (key, self.manifests[key].manifest_hash)
                    for key in sorted(self.manifests)
                ),
            }
        )

    @classmethod
    def default(cls, *, clock=lambda: "2026-01-01T00:00:00Z") -> ToolRegistry:
        created_at = clock()
        specs = (
            (
                "decimal_arithmetic",
                "Десятичная арифметика",
                "Decimal arithmetic",
                ("вычислить", "посчитать"),
                ("calculate", "compute"),
                {"operation": "enum", "operands": "canonical-decimal[2..16]"},
                {"result": "bounded canonical decimal"},
                tool_module.decimal_arithmetic,
            ),
            (
                "date_difference",
                "Разница дат",
                "Date difference",
                ("сколько дней между",),
                ("how many days between",),
                {"start_date": "ISO date", "end_date": "ISO date", "mode": "enum"},
                {"days": "integer"},
                tool_module.date_difference,
            ),
        )
        descriptors: dict[str, ToolDescriptor] = {}
        implementations: dict[str, ToolImplementation] = {}
        manifests: dict[str, ToolImplementationManifest] = {}
        for (
            tool_id,
            ru,
            en,
            aliases_ru,
            aliases_en,
            inputs,
            outputs,
            implementation,
        ) in specs:
            manifest = build_tool_implementation_manifest(tool_id, implementation)
            body = {
                "tool_id": tool_id,
                "version": 2,
                "canonical_name_ru": ru,
                "canonical_name_en": en,
                "aliases_ru": aliases_ru,
                "aliases_en": aliases_en,
                "input_schema": inputs,
                "output_schema": outputs,
                "execution_class": ToolExecutionClass.PURE_LOCAL_READ_ONLY,
                "deterministic": True,
                "network_required": False,
                "approval_policy": ToolApprovalPolicy.EXPLICIT_CONFIRMATION,
                "implementation_hash": manifest.manifest_hash,
                "implementation_manifest_hash": manifest.manifest_hash,
                "active": True,
                "deprecated": False,
                "created_at": created_at,
                "schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
            }
            descriptors[tool_id] = ToolDescriptor(
                **body, descriptor_hash=content_hash(body)
            )
            implementations[tool_id] = implementation
            manifests[tool_id] = manifest
        return cls(descriptors, implementations, manifests)

    def verify(self) -> None:
        if not (
            set(self.descriptors) == set(self._implementations) == set(self.manifests)
        ):
            raise ToolRegistryIntegrityError("tool registry components differ")
        for tool_id, descriptor in self.descriptors.items():
            body = asdict(descriptor)
            digest = body.pop("descriptor_hash")
            if content_hash(body) != digest:
                raise ToolRegistryIntegrityError(f"tool descriptor changed: {tool_id}")
            if descriptor.schema_version != TOOL_REGISTRY_SCHEMA_VERSION:
                raise ToolRegistryIntegrityError("incompatible tool registry schema")
            if (
                descriptor.network_required
                or descriptor.execution_class != ToolExecutionClass.PURE_LOCAL_READ_ONLY
            ):
                raise ToolRegistryIntegrityError(
                    "trusted registry contains unavailable tool"
                )
            manifest = self.manifests[tool_id]
            manifest_body = asdict(manifest)
            manifest_hash = manifest_body.pop("manifest_hash")
            if content_hash(manifest_body) != manifest_hash:
                raise ToolRegistryIntegrityError("tool implementation manifest changed")
            if descriptor.implementation_manifest_hash != manifest_hash:
                raise ToolRegistryIntegrityError("descriptor manifest binding mismatch")
            self.verify_current_implementation(tool_id)

    def verify_current_implementation(
        self, tool_id: str, expected_hash: str | None = None
    ) -> ToolImplementationManifest:
        current = build_tool_implementation_manifest(
            tool_id, self._implementations[tool_id]
        )
        expected = expected_hash or self.manifests[tool_id].manifest_hash
        if current.manifest_hash != expected:
            raise ToolImplementationStaleError(
                f"tool implementation is stale: {tool_id}"
            )
        return current

    def descriptor(self, tool_id: str) -> ToolDescriptor:
        try:
            descriptor = self.descriptors[tool_id]
        except KeyError as error:
            raise KeyError(f"unknown tool: {tool_id}") from error
        if not descriptor.active or descriptor.deprecated:
            raise ToolRegistryIntegrityError("tool is inactive")
        return descriptor

    def implementation_manifest(self, tool_id: str) -> ToolImplementationManifest:
        self.descriptor(tool_id)
        return self.manifests[tool_id]

    def manifest_hashes(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (key, self.manifests[key].manifest_hash) for key in sorted(self.manifests)
        )

    def current_manifest_hashes(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                key,
                build_tool_implementation_manifest(
                    key, self._implementations[key]
                ).manifest_hash,
            )
            for key in sorted(self._implementations)
        )

    def validate_and_canonicalize_arguments(
        self, tool_id: str, arguments: Any
    ) -> ToolArgumentValidation:
        try:
            self.descriptor(tool_id)
            if tool_id == "decimal_arithmetic":
                canonical = tool_module.validate_decimal_arguments(arguments)
            elif tool_id == "date_difference":
                canonical = tool_module.validate_date_arguments(arguments)
            else:
                raise ToolInputError("tool has no trusted argument validator")
        except (KeyError, ToolInputError, ToolRegistryIntegrityError) as error:
            return ToolArgumentValidation(
                tool_id=tool_id,
                status=ToolArgumentValidationStatus.INVALID,
                canonical_arguments=None,
                argument_hash=None,
                issues=(str(error),),
            )
        return ToolArgumentValidation(
            tool_id=tool_id,
            status=ToolArgumentValidationStatus.VALID,
            canonical_arguments=canonical,
            argument_hash=content_hash(canonical),
            issues=(),
        )

    def execute(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        expected_manifest_hash: str | None = None,
    ) -> dict[str, Any]:
        self.verify_current_implementation(tool_id, expected_manifest_hash)
        validation = self.validate_and_canonicalize_arguments(tool_id, arguments)
        if validation.status != ToolArgumentValidationStatus.VALID:
            raise ToolInputError(validation.issues[0])
        assert validation.canonical_arguments is not None
        return self._implementations[tool_id](validation.canonical_arguments)
