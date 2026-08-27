"""Chemistry-specific ToolRegistry preserving unified-router authority semantics."""

from __future__ import annotations

import inspect
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2 import trusted_decimal
from ai_brain.stage2.domains.chemistry import (
    calculations,
    formula_parser,
    knowledge_snapshot,
    models,
    provenance,
    resolver,
    source_derivation,
    tools,
    version,
)
from ai_brain.stage2.domains.chemistry.calculations import canonical_decimal
from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ATOMIC_WEIGHTS,
    AVOGADRO,
    build_knowledge_snapshot,
    snapshot_from_dict,
    snapshot_to_dict,
    verify_knowledge_snapshot,
)
from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.router.models import (
    ToolApprovalPolicy,
    ToolArgumentValidation,
    ToolArgumentValidationStatus,
    ToolDescriptor,
    ToolExecutionClass,
    ToolImplementationManifest,
)
from ai_brain.stage2.router.tool_registry import (
    ToolImplementationStaleError,
    ToolRegistry,
    ToolRegistryIntegrityError,
)
from ai_brain.stage2.router.tools import ToolInputError
from ai_brain.stage2.router.version import (
    TOOL_IMPLEMENTATION_POLICY_VERSION,
    TOOL_REGISTRY_SCHEMA_VERSION,
)

TOOL_IDS = (
    "chemistry_formula_composition",
    "chemistry_molar_mass",
    "chemistry_mass_amount",
    "chemistry_entity_amount",
)
CHEMISTRY_TOOL_INPUT_POLICY = version.CHEMISTRY_TOOL_INPUT_POLICY
CHEMISTRY_TOOL_NUMERIC_POLICY = "shared-bounded-decimal-v2"
CHEMISTRY_TOOL_OUTPUT_POLICY = "hashed-chemistry-result-bundle-v3"


def chemistry_tool_manifests() -> dict[str, ToolImplementationManifest]:
    modules = (
        calculations,
        formula_parser,
        knowledge_snapshot,
        models,
        provenance,
        resolver,
        source_derivation,
        tools,
        trusted_decimal,
        version,
    )
    helper_hashes = tuple(
        sorted(
            [
                (module.__name__, bytes_hash(Path(module.__file__).read_bytes()))
                for module in modules
            ]
            + [
                (
                    "ai_brain.stage2.domains.chemistry.tool_registry",
                    bytes_hash(Path(__file__).read_bytes()),
                )
            ]
        )
    )
    manifests = {}
    for tool_id in TOOL_IDS:
        implementation = getattr(tools, tool_id)
        body = {
            "tool_id": tool_id,
            "tool_version": 1,
            "module": implementation.__module__,
            "entry_function_qualified_name": implementation.__qualname__,
            "entry_function_source_hash": content_hash(
                inspect.getsource(implementation)
            ),
            "helper_function_source_hashes": helper_hashes,
            "constant_value_hashes": (
                (
                    "chemistry_domain_version",
                    content_hash(version.CHEMISTRY_DOMAIN_VERSION),
                ),
                ("formula_limits", content_hash(models.FormulaLimits())),
                (
                    "chemistry_quantity_limits",
                    content_hash(models.ChemistryQuantityLimits()),
                ),
                ("rounding_spec", content_hash(models.ChemistryRoundingSpec())),
            ),
            "input_normalization_policy": CHEMISTRY_TOOL_INPUT_POLICY,
            "numeric_context_policy": CHEMISTRY_TOOL_NUMERIC_POLICY,
            "output_canonicalization_policy": CHEMISTRY_TOOL_OUTPUT_POLICY,
            "runtime_contract": f"CPython>={platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}",
            "implementation_policy_version": TOOL_IMPLEMENTATION_POLICY_VERSION,
        }
        manifests[tool_id] = ToolImplementationManifest(
            **body, manifest_hash=content_hash(body)
        )
    return manifests


class ChemistryToolRegistry(ToolRegistry):
    def __init__(self, memory: FactMemory, domain_manifest: dict[str, Any]) -> None:
        self.memory = memory
        self.domain_manifest = domain_manifest
        self.domain_manifest_hash = domain_manifest["domain_manifest_hash"]
        self.supported_symbols = frozenset(
            item.external_identifiers["symbol"]
            for item in self.memory.list_entities(entity_type="chemical_element")
        )
        self._snapshot_cache: dict[
            tuple[str, tuple[str, ...], tuple[str, ...]], Any
        ] = {}
        self._trusted_snapshot_hashes: dict[str, str] = {}
        self.manifests = chemistry_tool_manifests()
        self._implementations = {
            tool_id: getattr(tools, tool_id) for tool_id in TOOL_IDS
        }
        names = {
            "chemistry_formula_composition": ("Состав формулы", "Formula composition"),
            "chemistry_molar_mass": ("Молярная масса", "Molar mass"),
            "chemistry_mass_amount": (
                "Масса и количество вещества",
                "Mass and amount of substance",
            ),
            "chemistry_entity_amount": (
                "Частицы и количество вещества",
                "Entities and amount of substance",
            ),
        }
        self.descriptors = {}
        for tool_id in TOOL_IDS:
            manifest = self.manifests[tool_id]
            body = {
                "tool_id": tool_id,
                "version": 1,
                "canonical_name_ru": names[tool_id][0],
                "canonical_name_en": names[tool_id][1],
                "aliases_ru": (),
                "aliases_en": (),
                "input_schema": {
                    "knowledge_snapshot": "immutable chemistry snapshot",
                    "arguments": "tool-specific bounded object",
                },
                "output_schema": {"result": "ChemistryResultBundle"},
                "execution_class": ToolExecutionClass.PURE_LOCAL_READ_ONLY,
                "deterministic": True,
                "network_required": False,
                "approval_policy": ToolApprovalPolicy.EXPLICIT_CONFIRMATION,
                "implementation_hash": manifest.manifest_hash,
                "implementation_manifest_hash": manifest.manifest_hash,
                "active": True,
                "deprecated": False,
                "created_at": "2026-08-27T00:00:00Z",
                "schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
            }
            self.descriptors[tool_id] = ToolDescriptor(
                **body, descriptor_hash=content_hash(body)
            )
        self.verify()
        self.registry_hash = content_hash(
            {
                "schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
                "descriptors": tuple(
                    asdict(self.descriptors[key]) for key in sorted(self.descriptors)
                ),
                "manifest_hashes": self.manifest_hashes(),
            }
        )

    def verify(self) -> None:
        if set(self.descriptors) != set(TOOL_IDS) or set(self.manifests) != set(
            TOOL_IDS
        ):
            raise ToolRegistryIntegrityError("chemistry registry components differ")
        current = chemistry_tool_manifests()
        for tool_id, descriptor in self.descriptors.items():
            body = asdict(descriptor)
            digest = body.pop("descriptor_hash")
            if content_hash(body) != digest:
                raise ToolRegistryIntegrityError("chemistry descriptor changed")
            if (
                descriptor.network_required
                or descriptor.approval_policy
                != ToolApprovalPolicy.EXPLICIT_CONFIRMATION
            ):
                raise ToolRegistryIntegrityError("unsafe chemistry tool descriptor")
            if current[tool_id].manifest_hash != self.manifests[tool_id].manifest_hash:
                raise ToolImplementationStaleError(
                    f"tool implementation is stale: {tool_id}"
                )

    def verify_current_implementation(
        self, tool_id: str, expected_hash: str | None = None
    ) -> ToolImplementationManifest:
        if tool_id not in TOOL_IDS:
            raise KeyError(f"unknown chemistry tool: {tool_id}")
        current = chemistry_tool_manifests()[tool_id]
        if current.manifest_hash != (
            expected_hash or self.manifests[tool_id].manifest_hash
        ):
            raise ToolImplementationStaleError(
                f"tool implementation is stale: {tool_id}"
            )
        return current

    def current_manifest_hashes(self) -> tuple[tuple[str, str], ...]:
        current = chemistry_tool_manifests()
        return tuple((key, current[key].manifest_hash) for key in sorted(current))

    def validate_and_canonicalize_arguments(
        self, tool_id: str, arguments: Any
    ) -> ToolArgumentValidation:
        try:
            self.descriptor(tool_id)
            canonical = self._canonical_arguments(tool_id, arguments)
        except (KeyError, TypeError, ValueError, ToolRegistryIntegrityError) as error:
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

    def _canonical_arguments(self, tool_id: str, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ToolInputError("chemistry arguments must be an object")
        raw = dict(arguments)
        supplied_snapshot = raw.pop("knowledge_snapshot", None)
        parser = FormulaParser(self.supported_symbols)
        selected_symbols: tuple[str, ...] = ()
        if "formula" in raw:
            selected_symbols = tuple(
                entry.symbol
                for entry in parser.parse(_text(raw["formula"], "formula")).composition
            )
        requirements = _tool_requirements(tool_id)
        snapshot = (
            self._current_snapshot(selected_symbols, requirements)
            if supplied_snapshot is None
            else snapshot_from_dict(supplied_snapshot)
        )
        snapshot_body = asdict(snapshot)
        snapshot_hash = snapshot_body.pop("snapshot_hash")
        if content_hash(snapshot_body) != snapshot_hash:
            raise ToolInputError("invalid or stale chemistry knowledge snapshot")
        if supplied_snapshot is not None and not self._is_trusted_snapshot(
            snapshot.snapshot_hash
        ):
            try:
                verify_knowledge_snapshot(snapshot, self.memory, self.domain_manifest)
            except ValueError as error:
                raise ToolInputError("stale chemistry knowledge snapshot") from error
        if snapshot.atomic_weight_policy != version.CHEMISTRY_ATOMIC_WEIGHT_POLICY:
            raise ToolInputError("stale chemistry knowledge snapshot")
        if tool_id == "chemistry_formula_composition":
            _exact_keys(raw, {"formula"})
            canonical = {
                "formula": parser.parse(
                    _text(raw["formula"], "formula")
                ).canonical_formula
            }
        elif tool_id == "chemistry_molar_mass":
            _allowed_keys(
                raw,
                {"formula", "mode", "unit"},
                {"significant_digits"},
            )
            canonical = {
                "formula": parser.parse(
                    _text(raw["formula"], "formula")
                ).canonical_formula,
                "mode": _choice(
                    raw["mode"],
                    {
                        "conventional",
                        "interval",
                        "CONVENTIONAL_CLASSROOM",
                        "NATURAL_VARIABILITY_ENVELOPE",
                    },
                    "mode",
                ),
                "unit": _choice(raw["unit"], {"g/mol", "kg/mol"}, "unit"),
                "significant_digits": _significant_digits(raw),
            }
        elif tool_id == "chemistry_mass_amount":
            _allowed_keys(
                raw,
                {"formula", "value", "source_unit", "target_unit"},
                {"significant_digits"},
            )
            source = _choice(
                raw["source_unit"], {"g", "kg", "mol", "mmol"}, "source_unit"
            )
            target = _choice(
                raw["target_unit"], {"g", "kg", "mol", "mmol"}, "target_unit"
            )
            if (source in {"g", "kg"}) == (target in {"g", "kg"}):
                raise ToolInputError(
                    "mass conversion must cross mass/amount dimensions"
                )
            canonical = {
                "formula": parser.parse(
                    _text(raw["formula"], "formula")
                ).canonical_formula,
                "value": canonical_decimal(raw["value"]),
                "source_unit": source,
                "target_unit": target,
                "significant_digits": _significant_digits(raw),
            }
        else:
            old_contract = set(raw) == {
                "value",
                "source_unit",
                "target_unit",
                "entity_type",
            }
            if not old_contract:
                _allowed_keys(
                    raw,
                    {"value", "source_unit", "target_unit", "basis", "formula"},
                    {
                        "target_element",
                        "requested_display_label",
                        "significant_digits",
                    },
                )
            source = _choice(
                raw["source_unit"], {"mol", "mmol", "entities"}, "source_unit"
            )
            target = _choice(
                raw["target_unit"], {"mol", "mmol", "entities"}, "target_unit"
            )
            if (source == "entities") == (target == "entities"):
                raise ToolInputError(
                    "entity conversion must cross entity/amount dimensions"
                )
            basis = (
                "FORMULA_ENTITIES"
                if old_contract
                else _choice(
                    raw["basis"],
                    {
                        "FORMULA_ENTITIES",
                        "TOTAL_ATOMS_IN_FORMULA",
                        "ATOMS_OF_ELEMENT_IN_FORMULA",
                    },
                    "basis",
                )
            )
            formula = None if old_contract else _text(raw["formula"], "formula")
            if formula is not None:
                formula = parser.parse(formula).canonical_formula
            canonical = {
                "value": canonical_decimal(raw["value"], integer=source == "entities"),
                "source_unit": source,
                "target_unit": target,
                "basis": basis,
                "formula": formula,
                "target_element": None
                if old_contract or raw.get("target_element") is None
                else _choice(
                    raw["target_element"], set(self.supported_symbols), "target_element"
                ),
                "requested_display_label": raw["entity_type"]
                if old_contract
                else _optional_text(raw.get("requested_display_label")),
                "significant_digits": _significant_digits(raw),
            }
        return {**canonical, "knowledge_snapshot": snapshot_to_dict(snapshot)}

    def execute(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        expected_manifest_hash: str | None = None,
    ) -> dict[str, Any]:
        self.verify_current_implementation(tool_id, expected_manifest_hash)
        validation = self.validate_and_canonicalize_arguments(tool_id, arguments)
        if validation.canonical_arguments is None:
            raise ToolInputError(validation.issues[0])
        canonical = dict(validation.canonical_arguments)
        snapshot = snapshot_from_dict(canonical.pop("knowledge_snapshot"))
        if not self._is_trusted_snapshot(snapshot.snapshot_hash):
            try:
                verify_knowledge_snapshot(snapshot, self.memory, self.domain_manifest)
            except ValueError as error:
                raise ToolInputError("stale chemistry knowledge snapshot") from error
        parser = FormulaParser(self.supported_symbols)
        return self._implementations[tool_id](canonical, parser, snapshot)

    def _current_snapshot(
        self, symbols: tuple[str, ...], requirements: tuple[str, ...]
    ):
        key = (
            self.memory.database.snapshot_hash(),
            tuple(sorted(symbols)),
            tuple(sorted(requirements)),
        )
        if key not in self._snapshot_cache:
            self._snapshot_cache[key] = build_knowledge_snapshot(
                self.memory,
                self.domain_manifest,
                key[1],
                requirements=key[2],
            )
            self._trusted_snapshot_hashes[self._snapshot_cache[key].snapshot_hash] = (
                key[0]
            )
        return self._snapshot_cache[key]

    def _is_trusted_snapshot(self, snapshot_hash: str) -> bool:
        return self._trusted_snapshot_hashes.get(snapshot_hash) == (
            self.memory.database.snapshot_hash()
        )


def _tool_requirements(tool_id: str) -> tuple[str, ...]:
    if tool_id in {"chemistry_molar_mass", "chemistry_mass_amount"}:
        return (ATOMIC_WEIGHTS,)
    if tool_id == "chemistry_entity_amount":
        return (AVOGADRO,)
    return ()


def _exact_keys(arguments: dict[str, Any], expected: set[str]) -> None:
    if set(arguments) != expected:
        raise ToolInputError(f"chemistry arguments require exactly {sorted(expected)}")


def _allowed_keys(
    arguments: dict[str, Any], required: set[str], optional: set[str]
) -> None:
    if not required <= set(arguments) or not set(arguments) <= required | optional:
        raise ToolInputError(
            f"chemistry arguments require {sorted(required)} and optional {sorted(optional)}"
        )


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ToolInputError(f"{name} must be non-empty text")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return _text(value, "requested_display_label")


def _significant_digits(arguments: dict[str, Any]) -> int:
    value = arguments.get("significant_digits", 6)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 12:
        raise ToolInputError("significant_digits must be an integer in 1..12")
    return value


def _choice(value: Any, choices: set[str], name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ToolInputError(f"unsupported {name}")
    return value
