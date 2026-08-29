"""Provider authority derived from real, locally verified bytes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.knowledge_ir.version import PROVIDER_REGISTRY_SCHEMA_VERSION
from ai_brain.stage3.providers.models import (
    ProviderManifest,
    ProviderStatus,
)

_ID = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


def provider_manifest_hash(value: ProviderManifest) -> str:
    body = asdict(value)
    body.pop("manifest_hash")
    return content_hash(body)


@dataclass(frozen=True)
class ProviderRegistry:
    root: str
    manifests: tuple[ProviderManifest, ...]
    schema_version: int
    registry_hash: str

    @classmethod
    def build(cls, root: Path, manifests: tuple[ProviderManifest, ...]):
        ordered = tuple(
            sorted(manifests, key=lambda item: (item.provider_id, item.version))
        )
        body = {
            "manifests": ordered,
            "schema_version": PROVIDER_REGISTRY_SCHEMA_VERSION,
        }
        resolved = root.resolve()
        stored_root = "." if resolved == Path.cwd().resolve() else str(resolved)
        result = cls(
            stored_root, ordered, PROVIDER_REGISTRY_SCHEMA_VERSION, content_hash(body)
        )
        result.verify()
        return result

    def verify(self) -> dict[str, object]:
        if self.schema_version != PROVIDER_REGISTRY_SCHEMA_VERSION:
            raise ValueError("unsupported provider registry schema")
        if self.registry_hash != content_hash(
            {"manifests": self.manifests, "schema_version": self.schema_version}
        ):
            raise ValueError("provider registry hash mismatch")
        keys: set[tuple[str, str]] = set()
        for manifest in self.manifests:
            _verify_manifest(Path(self.root), manifest)
            key = (manifest.provider_id, manifest.version)
            if key in keys:
                raise ValueError("duplicate provider manifest")
            keys.add(key)
        return {
            "status": "VERIFIED",
            "provider_count": len(keys),
            "registry_hash": self.registry_hash,
        }

    def manifest(
        self,
        provider_id: str,
        version: str | None = None,
        *,
        allow_deprecated: bool = False,
    ) -> ProviderManifest:
        matches = [
            item
            for item in self.manifests
            if item.provider_id == provider_id
            and (version is None or item.version == version)
            and (allow_deprecated or item.status is ProviderStatus.ACTIVE)
        ]
        if not matches:
            raise KeyError(provider_id)
        return max(matches, key=lambda item: _semver(item.version))

    def current_manifest(self, provider_id: str, version: str) -> ProviderManifest:
        self.verify()
        return self.manifest(provider_id, version)


def make_provider_manifest(**values) -> ProviderManifest:
    value = ProviderManifest(
        **values, schema_version=PROVIDER_REGISTRY_SCHEMA_VERSION, manifest_hash=""
    )
    return replace(value, manifest_hash=provider_manifest_hash(value))


def _verify_manifest(root: Path, value: ProviderManifest) -> None:
    if (
        value.schema_version != PROVIDER_REGISTRY_SCHEMA_VERSION
        or value.manifest_hash != provider_manifest_hash(value)
    ):
        raise ValueError("provider manifest hash or schema mismatch")
    if not _ID.fullmatch(value.provider_id) or not value.allowed_execution_contexts:
        raise ValueError("invalid provider identity or contexts")
    _semver(value.version)
    if value.status not in ProviderStatus:
        raise ValueError("invalid provider status")
    paths = (*value.implementation_sources, *value.transitive_helpers)
    if not value.implementation_sources or len(
        {item.relative_path for item in paths}
    ) != len(paths):
        raise ValueError("provider source manifest is incomplete or duplicated")
    for item in paths:
        _verify_file(root, item.relative_path, item.bytes_hash, "provider source")
    _verify_file(
        root, value.resource_policy_path, value.resource_policy_hash, "resource policy"
    )
    _verify_file(root, value.input_schema_path, value.input_schema_hash, "input schema")
    _verify_file(
        root, value.output_schema_path, value.output_schema_hash, "output schema"
    )


def _verify_file(root: Path, relative: str, expected: str, label: str) -> None:
    if not _HASH.fullmatch(expected):
        raise ValueError(f"invalid {label} hash")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes provider root") from error
    if (
        path.is_symlink()
        or not path.is_file()
        or bytes_hash(path.read_bytes()) != expected
    ):
        raise ValueError(f"{label} current bytes mismatch")


def _semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
    if not match:
        raise ValueError("provider version is not strict semver")
    return tuple(int(item) for item in match.groups())
