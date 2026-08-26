"""Separate checksummed registry for bounded local tools."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.router.models import (
    ToolApprovalPolicy,
    ToolDescriptor,
    ToolExecutionClass,
)
from ai_brain.stage2.router.tools import date_difference, decimal_arithmetic
from ai_brain.stage2.router.version import TOOL_REGISTRY_SCHEMA_VERSION

ToolImplementation = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistryIntegrityError(ValueError):
    pass


class ToolRegistry:
    def __init__(
        self,
        descriptors: dict[str, ToolDescriptor],
        implementations: dict[str, ToolImplementation],
    ) -> None:
        self.descriptors = dict(descriptors)
        self._implementations = dict(implementations)
        self.verify()
        self.registry_hash = content_hash(
            {
                "schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
                "descriptors": tuple(
                    asdict(self.descriptors[key]) for key in sorted(self.descriptors)
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
                {"operation": "ADD|SUBTRACT|MULTIPLY|DIVIDE", "operands": "decimal[]"},
                {"result": "canonical decimal"},
                decimal_arithmetic,
            ),
            (
                "date_difference",
                "Разница дат",
                "Date difference",
                ("сколько дней между",),
                ("how many days between",),
                {
                    "start_date": "ISO date",
                    "end_date": "ISO date",
                    "mode": "SIGNED|ABSOLUTE",
                },
                {"days": "integer"},
                date_difference,
            ),
        )
        descriptors: dict[str, ToolDescriptor] = {}
        implementations: dict[str, ToolImplementation] = {}
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
            implementation_hash = content_hash(
                {
                    "module": implementation.__module__,
                    "name": implementation.__qualname__,
                    "contract": inputs,
                    "source": inspect.getsource(implementation),
                }
            )
            body = {
                "tool_id": tool_id,
                "version": 1,
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
                "implementation_hash": implementation_hash,
                "active": True,
                "deprecated": False,
                "created_at": created_at,
                "schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
            }
            descriptor = ToolDescriptor(**body, descriptor_hash=content_hash(body))
            descriptors[tool_id] = descriptor
            implementations[tool_id] = implementation
        return cls(descriptors, implementations)

    def verify(self) -> None:
        if set(self.descriptors) != set(self._implementations):
            raise ToolRegistryIntegrityError(
                "tool descriptors and implementations differ"
            )
        for tool_id, descriptor in self.descriptors.items():
            body = asdict(descriptor)
            digest = body.pop("descriptor_hash")
            if digest != descriptor.descriptor_hash or content_hash(body) != digest:
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

    def descriptor(self, tool_id: str) -> ToolDescriptor:
        try:
            descriptor = self.descriptors[tool_id]
        except KeyError as error:
            raise KeyError(f"unknown tool: {tool_id}") from error
        if not descriptor.active or descriptor.deprecated:
            raise ToolRegistryIntegrityError("tool is inactive")
        return descriptor

    def execute(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.descriptor(tool_id)
        return self._implementations[tool_id](arguments)
