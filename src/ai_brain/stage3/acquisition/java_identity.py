"""Canonical, case-sensitive Java callable identity for production trust."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_release import JavaReleaseIdentity
from ai_brain.stage3.acquisition.java_source_index import (
    UNRESOLVED_DESCRIPTOR,
    JavaDeclaration,
)

JAVA_CALLABLE_IDENTITY_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class JavaCanonicalCallableIdentity:
    schema_version: int
    target_release: int
    release_identity_hash: str
    module_identity: str
    binary_receiver_identity: str
    callable_kind: str
    member_name: str
    erased_parameter_descriptor: str
    source_scope: str
    identity_hash: str

    @property
    def runtime_key(self) -> tuple[str, str, str, str, str]:
        """Classpath uniqueness key; return type and source scope are excluded."""

        return (
            self.module_identity,
            self.binary_receiver_identity,
            self.callable_kind,
            self.member_name,
            self.erased_parameter_descriptor,
        )

    @property
    def exact_reference(self) -> str:
        return (
            f"java:{self.target_release}/{self.module_identity}@{self.source_scope}/"
            f"{self.binary_receiver_identity}#{self.member_name}"
            f"({self.erased_parameter_descriptor})"
        )


def canonical_java_callable_identity(
    declaration: JavaDeclaration,
    release: JavaReleaseIdentity,
) -> JavaCanonicalCallableIdentity:
    """Build an immutable identity from resolved JVM parameter erasures."""

    if declaration.member_kind not in {"method", "constructor"}:
        raise ValueError("Java callable identity requires a method or constructor")
    descriptor = declaration.erased_jvm_descriptor
    if descriptor == UNRESOLVED_DESCRIPTOR:
        raise ValueError("unresolved Java declaration has no callable identity")
    start = descriptor.find("(")
    end = descriptor.find(")", start + 1)
    if start < 0 or end < 0:
        raise ValueError("invalid JVM callable descriptor")
    parameter_descriptor = descriptor[start + 1 : end]
    names = (declaration.top_level_type_name, *declaration.nested_type_path)
    owner = "$".join(names)
    if declaration.package_name:
        owner = f"{declaration.package_name}.{owner}"
    kind = "CONSTRUCTOR" if declaration.member_kind == "constructor" else "METHOD"
    body = {
        "schema_version": JAVA_CALLABLE_IDENTITY_SCHEMA_VERSION,
        "target_release": release.source_compatibility_release,
        "release_identity_hash": release.identity_hash,
        "module_identity": declaration.module_name or "UNNAMED",
        "binary_receiver_identity": owner,
        "callable_kind": kind,
        "member_name": "<init>" if kind == "CONSTRUCTOR" else declaration.member_name,
        "erased_parameter_descriptor": parameter_descriptor,
        "source_scope": declaration.source_unit_id.partition("/")[0],
    }
    return JavaCanonicalCallableIdentity(**body, identity_hash=content_hash(body))


def verify_java_callable_identity(identity: JavaCanonicalCallableIdentity) -> None:
    body = asdict(identity)
    claimed = body.pop("identity_hash")
    if (
        identity.schema_version != JAVA_CALLABLE_IDENTITY_SCHEMA_VERSION
        or identity.target_release <= 0
        or identity.callable_kind not in {"METHOD", "CONSTRUCTOR"}
        or (identity.callable_kind == "CONSTRUCTOR")
        != (identity.member_name == "<init>")
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid canonical Java callable identity")
