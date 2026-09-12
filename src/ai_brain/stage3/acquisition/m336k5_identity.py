"""Typed, non-interchangeable identities for the M-33.6k.5 final route."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar, Self

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

M336K5_ROUTE_VERSION = "m336k5.candidate-isolated-java-final-route.v1"
M336K5_PROTOCOL_RUN_ID = "m336k5.final-java.outcome-a.v1"
M336K5_ACQUISITION_RUN_ID = "m336k5.final-java.global-acquisition.v1"
M336K5_SELECTOR_RUN_ID = "m336k5.final-java.selector.v1"
M336K5_EVALUATOR_RUN_ID = "m336k5.final-java.evaluator.v1"

_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, eq=False)
class _M336K5Identity:
    """Base codec whose equality deliberately requires the same semantic type."""

    value: str
    schema_version: int = 1

    identity_kind: ClassVar[str]
    namespace: ClassVar[re.Pattern[str]]
    official_value: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise M336K2ProtocolError("M336K5 identity schema version is invalid")
        if type(self.value) is not str or not self.value:
            raise M336K2ProtocolError("M336K5 identity is empty")
        if self.value != self.value.strip():
            raise M336K2ProtocolError("M336K5 identity contains surrounding whitespace")
        if (
            not self.value.isascii()
            or unicodedata.normalize("NFKC", self.value) != self.value
        ):
            raise M336K2ProtocolError("M336K5 identity contains a Unicode confusable")
        if self.namespace.fullmatch(self.value) is None:
            raise M336K2ProtocolError(
                f"M336K5 {self.identity_kind} namespace is invalid"
            )
        if ".final-java." in self.value and self.official_value != self.value:
            raise M336K2ProtocolError(
                f"M336K5 {self.identity_kind} final identity is not canonical"
            )

    def __eq__(self, other: object) -> bool:
        return (
            type(self) is type(other)
            and self.canonical_object() == other.canonical_object()
        )

    def __hash__(self) -> int:
        return hash((type(self), self.value, self.schema_version))

    @property
    def identity_hash(self) -> str:
        return content_hash(self._body())

    def _body(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "identity_kind": self.identity_kind,
            "value": self.value,
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "identity_hash": self.identity_hash}

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_object())

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        if type(value) is not dict or set(value) != {
            "schema_version",
            "identity_kind",
            "value",
            "identity_hash",
        }:
            raise M336K2ProtocolError(
                f"M336K5 {cls.identity_kind} codec fields changed"
            )
        if value.get("identity_kind") != cls.identity_kind:
            raise M336K2ProtocolError(f"M336K5 {cls.identity_kind} type was confused")
        result = cls(
            value=value.get("value"), schema_version=value.get("schema_version")
        )
        if value.get("identity_hash") != result.identity_hash:
            raise M336K2ProtocolError(f"M336K5 {cls.identity_kind} hash changed")
        return result


@dataclass(frozen=True, eq=False)
class M336K5RouteVersion(_M336K5Identity):
    identity_kind: ClassVar[str] = "ROUTE_VERSION"
    namespace: ClassVar[re.Pattern[str]] = re.compile(
        r"m336k5\.candidate-isolated-java-(?:final|disposable)-route\.v[1-9][0-9]*"
    )
    official_value: ClassVar[str] = M336K5_ROUTE_VERSION


@dataclass(frozen=True, eq=False)
class M336K5ProtocolRunId(_M336K5Identity):
    identity_kind: ClassVar[str] = "PROTOCOL_RUN_ID"
    namespace: ClassVar[re.Pattern[str]] = re.compile(
        r"m336k5\.(?:final-java\.outcome-a|disposable\.[a-z0-9-]+)\.v[1-9][0-9]*"
    )
    official_value: ClassVar[str] = M336K5_PROTOCOL_RUN_ID


@dataclass(frozen=True, eq=False)
class M336K5AcquisitionRunId(_M336K5Identity):
    identity_kind: ClassVar[str] = "ACQUISITION_RUN_ID"
    namespace: ClassVar[re.Pattern[str]] = re.compile(
        r"m336k5\.(?:final-java\.global-acquisition|disposable\.[a-z0-9-]+\.acquisition)\.v[1-9][0-9]*"
    )
    official_value: ClassVar[str] = M336K5_ACQUISITION_RUN_ID


@dataclass(frozen=True, eq=False)
class M336K5SelectorRunId(_M336K5Identity):
    identity_kind: ClassVar[str] = "SELECTOR_RUN_ID"
    namespace: ClassVar[re.Pattern[str]] = re.compile(
        r"m336k5\.(?:final-java\.selector|disposable\.[a-z0-9-]+\.selector)\.v[1-9][0-9]*"
    )
    official_value: ClassVar[str] = M336K5_SELECTOR_RUN_ID


@dataclass(frozen=True, eq=False)
class M336K5EvaluatorRunId(_M336K5Identity):
    identity_kind: ClassVar[str] = "EVALUATOR_RUN_ID"
    namespace: ClassVar[re.Pattern[str]] = re.compile(
        r"m336k5\.(?:final-java\.evaluator|disposable\.[a-z0-9-]+\.evaluator)\.v[1-9][0-9]*"
    )
    official_value: ClassVar[str] = M336K5_EVALUATOR_RUN_ID


@dataclass(frozen=True, eq=False)
class M336K5RouteComponentId(_M336K5Identity):
    identity_kind: ClassVar[str] = "ROUTE_COMPONENT_ID"
    namespace: ClassVar[re.Pattern[str]] = re.compile(
        r"m336k5\.route-component\.[a-z][a-z0-9-]*\.v[1-9][0-9]*"
    )


@dataclass(frozen=True, eq=False)
class M336K5ExecutionMode(_M336K5Identity):
    identity_kind: ClassVar[str] = "EXECUTION_MODE"
    namespace: ClassVar[re.Pattern[str]] = re.compile(r"FINAL")
    official_value: ClassVar[str] = "FINAL"


@dataclass(frozen=True)
class M336K5RouteIdentityBundle:
    schema_version: int
    route_version: M336K5RouteVersion
    protocol_run_id: M336K5ProtocolRunId
    acquisition_run_id: M336K5AcquisitionRunId
    selector_run_id: M336K5SelectorRunId
    evaluator_run_id: M336K5EvaluatorRunId
    execution_mode: M336K5ExecutionMode
    route_registry_hash: str
    route_manifest_hash: str
    acquisition_policy_hash: str
    selector_policy_hash: str
    evaluator_policy_hash: str
    bundle_hash: str

    def _body(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "route_version": self.route_version.canonical_object(),
            "protocol_run_id": self.protocol_run_id.canonical_object(),
            "acquisition_run_id": self.acquisition_run_id.canonical_object(),
            "selector_run_id": self.selector_run_id.canonical_object(),
            "evaluator_run_id": self.evaluator_run_id.canonical_object(),
            "execution_mode": self.execution_mode.canonical_object(),
            "route_registry_hash": self.route_registry_hash,
            "route_manifest_hash": self.route_manifest_hash,
            "acquisition_policy_hash": self.acquisition_policy_hash,
            "selector_policy_hash": self.selector_policy_hash,
            "evaluator_policy_hash": self.evaluator_policy_hash,
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "bundle_hash": self.bundle_hash}

    @classmethod
    def build(
        cls,
        *,
        route_version: M336K5RouteVersion,
        protocol_run_id: M336K5ProtocolRunId,
        acquisition_run_id: M336K5AcquisitionRunId,
        selector_run_id: M336K5SelectorRunId,
        evaluator_run_id: M336K5EvaluatorRunId,
        execution_mode: M336K5ExecutionMode,
        route_registry_hash: str,
        route_manifest_hash: str,
        acquisition_policy_hash: str,
        selector_policy_hash: str,
        evaluator_policy_hash: str,
    ) -> Self:
        values = {
            "schema_version": 1,
            "route_version": route_version,
            "protocol_run_id": protocol_run_id,
            "acquisition_run_id": acquisition_run_id,
            "selector_run_id": selector_run_id,
            "evaluator_run_id": evaluator_run_id,
            "execution_mode": execution_mode,
            "route_registry_hash": route_registry_hash,
            "route_manifest_hash": route_manifest_hash,
            "acquisition_policy_hash": acquisition_policy_hash,
            "selector_policy_hash": selector_policy_hash,
            "evaluator_policy_hash": evaluator_policy_hash,
        }
        temporary = cls(**values, bundle_hash="0" * 64)
        result = cls(**values, bundle_hash=content_hash(temporary._body()))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 route identity bundle fields changed")
        result = cls(
            schema_version=value.get("schema_version"),
            route_version=M336K5RouteVersion.from_dict(value.get("route_version")),
            protocol_run_id=M336K5ProtocolRunId.from_dict(value.get("protocol_run_id")),
            acquisition_run_id=M336K5AcquisitionRunId.from_dict(
                value.get("acquisition_run_id")
            ),
            selector_run_id=M336K5SelectorRunId.from_dict(value.get("selector_run_id")),
            evaluator_run_id=M336K5EvaluatorRunId.from_dict(
                value.get("evaluator_run_id")
            ),
            execution_mode=M336K5ExecutionMode.from_dict(value.get("execution_mode")),
            route_registry_hash=value.get("route_registry_hash"),
            route_manifest_hash=value.get("route_manifest_hash"),
            acquisition_policy_hash=value.get("acquisition_policy_hash"),
            selector_policy_hash=value.get("selector_policy_hash"),
            evaluator_policy_hash=value.get("evaluator_policy_hash"),
            bundle_hash=value.get("bundle_hash"),
        )
        result.verify()
        return result

    def verify(self) -> None:
        hashes = (
            self.route_registry_hash,
            self.route_manifest_hash,
            self.acquisition_policy_hash,
            self.selector_policy_hash,
            self.evaluator_policy_hash,
            self.bundle_hash,
        )
        if (
            self.schema_version != 1
            or any(
                type(value) is not str or _HASH.fullmatch(value) is None
                for value in hashes
            )
            or self.bundle_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K5 route identity bundle is invalid")


def build_m336k5_official_identity_bundle(**hashes: str) -> M336K5RouteIdentityBundle:
    return M336K5RouteIdentityBundle.build(
        route_version=M336K5RouteVersion(M336K5_ROUTE_VERSION),
        protocol_run_id=M336K5ProtocolRunId(M336K5_PROTOCOL_RUN_ID),
        acquisition_run_id=M336K5AcquisitionRunId(M336K5_ACQUISITION_RUN_ID),
        selector_run_id=M336K5SelectorRunId(M336K5_SELECTOR_RUN_ID),
        evaluator_run_id=M336K5EvaluatorRunId(M336K5_EVALUATOR_RUN_ID),
        execution_mode=M336K5ExecutionMode("FINAL"),
        **hashes,
    )
