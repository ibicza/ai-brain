"""Checksummed Stage-2 SkillRegistry bound to verified RuleMemory records."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ai_brain.rules.memory import RuleMemory, RuleRecord
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.stage1.models import (
    InstalledRuleReceipt,
    SemanticFamily,
    content_hash,
    specification_hash,
    utc_now,
)
from ai_brain.stage1.specifications import infer_family
from ai_brain.stage1.version import STAGE1_VERSION
from ai_brain.stage2.catalog import controlled_command
from ai_brain.stage2.models import SkillRecord, SkillRegistryManifest
from ai_brain.stage2.version import (
    SKILL_REGISTRY_SCHEMA_VERSION,
    STAGE2_SCHEMA_VERSION,
    ensure_stage1_compatible,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROOT_FIELDS = {"schema_version", "manifest", "records", "content_sha256"}


class SkillRegistryIntegrityError(ValueError):
    pass


class SkillRegistryStaleError(RuntimeError):
    pass


class SkillRegistryRecoveryError(RuntimeError):
    pass


class SkillRegistryRecoveryRequiredError(RuntimeError):
    pass


class SkillRegistry:
    def __init__(
        self,
        records: Mapping[str, SkillRecord],
        manifest: SkillRegistryManifest,
        *,
        recovery_source: str = "new",
    ) -> None:
        self.records = MappingProxyType(dict(records))
        self.manifest = manifest
        self.recovery_source = recovery_source

    def active_records(self) -> list[SkillRecord]:
        return [
            record
            for record in self.records.values()
            if record.active and not record.deprecated
        ]

    def validate_against_rule_memory(self, memory: RuleMemory) -> None:
        ensure_stage1_compatible()
        errors: list[str] = []
        if self.manifest.stage1_version != STAGE1_VERSION:
            errors.append("incompatible Stage-1 version")
        actual_memory_hash = rule_memory_hash(memory)
        if self.manifest.rule_memory_hash != actual_memory_hash:
            errors.append("RuleMemory changed after registry build")
        active_semantics: set[str] = set()
        for skill_id, skill in self.records.items():
            if skill_id != skill.skill_id:
                errors.append(f"skill key mismatch: {skill_id}")
            rule = memory.records.get(skill.rule_id)
            if rule is None:
                errors.append(f"orphan skill: {skill_id}")
                continue
            if skill.active:
                if rule.deprecated:
                    errors.append(f"deprecated rule selected: {skill.rule_id}")
                if rule.status not in {
                    VerificationStatus.FORMALLY_VERIFIED,
                    VerificationStatus.PROPERTY_VERIFIED,
                }:
                    errors.append(f"unverified rule: {skill.rule_id}")
                if skill.rule_semantic_hash in active_semantics:
                    errors.append("duplicate active semantic skill")
                active_semantics.add(skill.rule_semantic_hash)
            if rule.semantic_hash != skill.rule_semantic_hash:
                errors.append(f"rule semantic hash mismatch: {skill.skill_id}")
            if specification_hash(rule.specification) != skill.specification_hash:
                errors.append(f"specification hash mismatch: {skill.skill_id}")
            if rule.version != skill.rule_version:
                errors.append(f"rule version mismatch: {skill.skill_id}")
            if _binding_hash(skill.provenance, rule) != skill.installed_receipt_hash:
                errors.append(f"installation binding mismatch: {skill.skill_id}")
            _validate_language_metadata(skill, errors)
        if len(self.active_records()) != self.manifest.active_skill_count:
            errors.append("active skill count mismatch")
        if registry_hash(self.records, self.manifest) != self.manifest.registry_hash:
            errors.append("registry hash mismatch")
        if errors:
            raise SkillRegistryStaleError("; ".join(errors))

    def update_skill_metadata(
        self,
        skill_id: str,
        *,
        aliases_ru: tuple[str, ...] | None = None,
        aliases_en: tuple[str, ...] | None = None,
    ) -> SkillRegistry:
        if skill_id not in self.records:
            raise KeyError(skill_id)
        now = utc_now()
        records = dict(self.records)
        current = records[skill_id]
        records[skill_id] = replace(
            current,
            aliases_ru=current.aliases_ru if aliases_ru is None else aliases_ru,
            aliases_en=current.aliases_en if aliases_en is None else aliases_en,
            updated_at=now,
        )
        manifest = _build_manifest(
            records,
            self.manifest.rule_memory_hash,
            self.manifest.registry_version + 1,
            created_at=self.manifest.created_at,
            updated_at=now,
        )
        return SkillRegistry(records, manifest)

    def save(self, path: Path) -> None:
        if self.recovery_source.startswith("backup:"):
            raise SkillRegistryRecoveryRequiredError(
                "Explicit registry recovery is required before writing"
            )
        rendered = _render(self)
        self._load_text(rendered, source="temporary validation")
        backup = path.with_suffix(path.suffix + ".bak")
        if path.exists():
            try:
                current = path.read_bytes()
                self.load(path)
            except (OSError, SkillRegistryIntegrityError) as exc:
                raise SkillRegistryRecoveryRequiredError(
                    "Explicit registry recovery is required before writing"
                ) from exc
            _atomic_write(backup, current)
            self.load(backup)
        _atomic_write(path, rendered.encode("utf-8"))
        self.load(path)

    @classmethod
    def load(cls, path: Path) -> SkillRegistry:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SkillRegistryIntegrityError(f"Registry read failed: {exc}") from exc
        return cls._load_text(text, source="primary")

    @classmethod
    def load_with_backup(cls, path: Path) -> SkillRegistry:
        try:
            registry = cls.load(path)
            registry.recovery_source = "primary"
            return registry
        except SkillRegistryIntegrityError as primary_error:
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                raise
            try:
                registry = cls.load(backup)
            except SkillRegistryIntegrityError as backup_error:
                raise SkillRegistryRecoveryError(
                    f"Both registry primary and backup are invalid: "
                    f"primary={primary_error}; backup={backup_error}"
                ) from backup_error
            registry.recovery_source = f"backup:{backup}"
            return registry

    @classmethod
    def _load_text(cls, text: str, *, source: str) -> SkillRegistry:
        try:
            row = json.loads(text)
            if not isinstance(row, dict) or set(row) != _ROOT_FIELDS:
                raise TypeError("root schema mismatch")
            if row["schema_version"] != SKILL_REGISTRY_SCHEMA_VERSION:
                raise ValueError("unsupported registry schema")
            checksum = row["content_sha256"]
            if not isinstance(checksum, str) or _SHA256.fullmatch(checksum) is None:
                raise ValueError("missing or malformed mandatory checksum")
            body = {key: value for key, value in row.items() if key != "content_sha256"}
            if content_hash(body) != checksum:
                raise ValueError("registry checksum mismatch")
            manifest = _manifest_from_json(row["manifest"])
            records_row = row["records"]
            if not isinstance(records_row, list):
                raise TypeError("records must be an array")
            records = [_record_from_json(item) for item in records_row]
            if len({item.skill_id for item in records}) != len(records):
                raise ValueError("duplicate skill ID")
            registry = cls(
                {item.skill_id: item for item in records},
                manifest,
                recovery_source=source,
            )
            if registry_hash(registry.records, manifest) != manifest.registry_hash:
                raise ValueError("registry manifest hash mismatch")
            return registry
        except SkillRegistryIntegrityError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise SkillRegistryIntegrityError(f"Corrupt SkillRegistry: {exc}") from exc


def rebuild_from_rule_memory(
    memory: RuleMemory,
    *,
    receipts: Mapping[str, InstalledRuleReceipt] | None = None,
    registry_version: int = 1,
) -> SkillRegistry:
    ensure_stage1_compatible()
    now = utc_now()
    records: dict[str, SkillRecord] = {}
    for rule in memory.active_records():
        skill = _skill_from_rule(rule, (receipts or {}).get(rule.rule_id), now)
        if skill.skill_id in records:
            raise SkillRegistryIntegrityError(f"duplicate skill ID {skill.skill_id}")
        if any(
            item.rule_semantic_hash == skill.rule_semantic_hash
            for item in records.values()
        ):
            raise SkillRegistryIntegrityError("duplicate active semantic skill")
        records[skill.skill_id] = skill
    memory_hash = rule_memory_hash(memory)
    manifest = _build_manifest(
        records,
        memory_hash,
        registry_version,
        created_at=now,
        updated_at=now,
    )
    registry = SkillRegistry(records, manifest)
    registry.validate_against_rule_memory(memory)
    return registry


def _build_manifest(
    records: Mapping[str, SkillRecord],
    memory_hash: str,
    registry_version: int,
    *,
    created_at: str,
    updated_at: str,
) -> SkillRegistryManifest:
    placeholder = SkillRegistryManifest(
        registry_version=registry_version,
        registry_hash="0" * 64,
        rule_memory_hash=memory_hash,
        stage1_version=STAGE1_VERSION,
        stage2_schema_version=STAGE2_SCHEMA_VERSION,
        skill_count=len(records),
        active_skill_count=len(records),
        family_counts=dict(Counter(item.semantic_family for item in records.values())),
        alias_count=sum(
            len(item.aliases_ru) + len(item.aliases_en) for item in records.values()
        ),
        description_count=sum(
            2 + len(item.controlled_examples_ru) + len(item.controlled_examples_en)
            for item in records.values()
        ),
        created_at=created_at,
        updated_at=updated_at,
    )
    manifest = SkillRegistryManifest(
        **{
            **asdict(placeholder),
            "registry_hash": registry_hash(records, placeholder),
        }
    )
    return manifest


def recover_skill_registry(path: Path) -> dict[str, Any]:
    try:
        SkillRegistry.load(path)
    except SkillRegistryIntegrityError:
        pass
    else:
        raise SkillRegistryRecoveryRequiredError("Registry primary is already valid")
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        SkillRegistry.load(backup)
        primary_bytes = path.read_bytes()
        backup_bytes = backup.read_bytes()
    except (OSError, SkillRegistryIntegrityError) as exc:
        raise SkillRegistryRecoveryError(f"Registry recovery failed: {exc}") from exc
    timestamp = datetime.now(UTC)
    corrupt = path.with_name(
        f"{path.name}.{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}.corrupt"
    )
    _atomic_write(corrupt, primary_bytes)
    _atomic_write(path, backup_bytes)
    restored = SkillRegistry.load(path)
    return {
        "primary": str(path),
        "backup": str(backup),
        "preserved_corrupt_primary": str(corrupt),
        "corrupt_primary_sha256": hashlib.sha256(primary_bytes).hexdigest(),
        "restored_primary_sha256": hashlib.sha256(backup_bytes).hexdigest(),
        "registry_hash": restored.manifest.registry_hash,
        "record_count": len(restored.records),
        "recovered_at": timestamp.isoformat(),
    }


def rule_memory_hash(memory: RuleMemory) -> str:
    return content_hash(
        {
            "allow_hypothesis_identified": memory.allow_hypothesis_identified,
            "records": [asdict(memory.records[key]) for key in sorted(memory.records)],
        }
    )


def registry_hash(
    records: Mapping[str, SkillRecord], manifest: SkillRegistryManifest
) -> str:
    manifest_row = asdict(manifest)
    manifest_row["registry_hash"] = "0" * 64
    return content_hash(
        {
            "manifest": manifest_row,
            "records": [asdict(records[key]) for key in sorted(records)],
        }
    )


def _skill_from_rule(
    rule: RuleRecord, receipt: InstalledRuleReceipt | None, now: str
) -> SkillRecord:
    family = infer_family(rule.specification)
    if family is None:
        raise SkillRegistryIntegrityError(
            f"unsupported rule specification {rule.rule_id}"
        )
    sources = tuple(rule.specification.inputs)
    destination = rule.specification.outputs[0] if rule.specification.outputs else None
    names = _names(family, sources, destination)
    if receipt is not None:
        _validate_receipt(rule, receipt)
        binding = {"binding_kind": "INSTALLED_RECEIPT", "receipt": asdict(receipt)}
        binding_hash = content_hash(receipt)
    else:
        try:
            provenance = json.loads(rule.provenance)
        except (json.JSONDecodeError, TypeError):
            provenance = {"raw_provenance_hash": content_hash(rule.provenance)}
        binding = {"binding_kind": "RULE_PROVENANCE", "provenance": provenance}
        binding_hash = content_hash(provenance)
    return SkillRecord(
        skill_id=f"skill-{rule.semantic_hash[:20]}",
        rule_id=rule.rule_id,
        rule_semantic_hash=rule.semantic_hash,
        specification_hash=specification_hash(rule.specification),
        installed_receipt_hash=binding_hash,
        rule_version=rule.version,
        active=not rule.deprecated,
        deprecated=rule.deprecated,
        canonical_name_ru=names[0],
        canonical_name_en=names[1],
        aliases_ru=(controlled_command(family, sources, destination, "ru"),),
        aliases_en=(controlled_command(family, sources, destination, "en"),),
        controlled_examples_ru=(
            controlled_command(family, sources, destination, "ru", extended=True),
        ),
        controlled_examples_en=(
            controlled_command(family, sources, destination, "en", extended=True),
        ),
        effect_summary=_effect_summary(family, sources, destination),
        input_state_schema=("R0", "R1", "R2", "R3"),
        effect_schema=asdict(rule.specification),
        preconditions=("non-negative bounded register state",),
        postconditions=tuple(_postconditions(rule.specification)),
        supported_languages=("ru", "en"),
        semantic_family=str(family),
        provenance=binding,
        created_at=now,
        updated_at=now,
    )


def _validate_receipt(rule: RuleRecord, receipt: InstalledRuleReceipt) -> None:
    if receipt.installed_rule_id != rule.rule_id:
        raise SkillRegistryIntegrityError("receipt rule ID mismatch")
    if receipt.rule_semantic_hash != rule.semantic_hash:
        raise SkillRegistryIntegrityError("receipt semantic hash mismatch")
    if receipt.specification_hash != specification_hash(rule.specification):
        raise SkillRegistryIntegrityError("receipt specification hash mismatch")


def _binding_hash(provenance: dict[str, Any], rule: RuleRecord) -> str:
    if provenance.get("binding_kind") == "INSTALLED_RECEIPT":
        receipt = provenance.get("receipt")
        if not isinstance(receipt, dict):
            return ""
        if receipt.get("installed_rule_id") != rule.rule_id:
            return ""
        if receipt.get("rule_semantic_hash") != rule.semantic_hash:
            return ""
        if receipt.get("specification_hash") != specification_hash(rule.specification):
            return ""
        return content_hash(receipt)
    value = provenance.get("provenance")
    return content_hash(value) if isinstance(value, dict) else ""


def _names(
    family: SemanticFamily, sources: tuple[str, ...], destination: str | None
) -> tuple[str, str]:
    roles = " ".join(sources)
    target = f" -> {destination}" if destination else ""
    return (
        f"{family.value}: {roles}{target}",
        f"{family.value}: {roles}{target}",
    )


def _effect_summary(
    family: SemanticFamily, sources: tuple[str, ...], destination: str | None
) -> str:
    return (
        f"family={family.value}; sources={','.join(sources) or 'none'}; "
        f"destination={destination or 'none'}"
    )


def _postconditions(specification) -> list[str]:
    rows = [f"{source}=0" for source in specification.terminate_when_empty]
    rows.extend(f"preserve {register}" for register in specification.preserve)
    return rows or ["state unchanged"]


def _validate_language_metadata(skill: SkillRecord, errors: list[str]) -> None:
    values = (
        skill.canonical_name_ru,
        skill.canonical_name_en,
        *skill.aliases_ru,
        *skill.aliases_en,
        *skill.controlled_examples_ru,
        *skill.controlled_examples_en,
    )
    if any(not isinstance(value, str) or not value.strip() for value in values):
        errors.append(f"malformed language metadata: {skill.skill_id}")
    if set(skill.supported_languages) != {"ru", "en"}:
        errors.append(f"malformed supported languages: {skill.skill_id}")


def _render(registry: SkillRegistry) -> str:
    body = {
        "schema_version": SKILL_REGISTRY_SCHEMA_VERSION,
        "manifest": asdict(registry.manifest),
        "records": [asdict(registry.records[key]) for key in sorted(registry.records)],
    }
    return (
        json.dumps(
            {**body, "content_sha256": content_hash(body)},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _manifest_from_json(value: Any) -> SkillRegistryManifest:
    if not isinstance(value, dict) or set(value) != {
        item.name for item in fields(SkillRegistryManifest)
    }:
        raise TypeError("manifest schema mismatch")
    manifest = SkillRegistryManifest(**value)
    if not isinstance(manifest.registry_version, int) or isinstance(
        manifest.registry_version, bool
    ):
        raise TypeError("invalid registry version")
    if _SHA256.fullmatch(manifest.registry_hash) is None:
        raise ValueError("invalid registry hash")
    if _SHA256.fullmatch(manifest.rule_memory_hash) is None:
        raise ValueError("invalid RuleMemory hash")
    for name in (
        "stage2_schema_version",
        "skill_count",
        "active_skill_count",
        "alias_count",
        "description_count",
    ):
        item = getattr(manifest, name)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypeError(f"invalid manifest {name}")
    if manifest.stage2_schema_version != STAGE2_SCHEMA_VERSION:
        raise ValueError("unsupported Stage-2 manifest schema")
    if not isinstance(manifest.stage1_version, str) or not manifest.stage1_version:
        raise TypeError("invalid manifest Stage-1 version")
    if not isinstance(manifest.family_counts, dict) or any(
        not isinstance(key, str)
        or not key
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        for key, count in manifest.family_counts.items()
    ):
        raise TypeError("invalid manifest family counts")
    for name in ("created_at", "updated_at"):
        _validate_timestamp(getattr(manifest, name), f"manifest {name}")
    return manifest


def _record_from_json(value: Any) -> SkillRecord:
    expected = {item.name for item in fields(SkillRecord)}
    if not isinstance(value, dict) or set(value) != expected:
        raise TypeError("skill record schema mismatch")
    tuple_fields = {
        "aliases_ru",
        "aliases_en",
        "controlled_examples_ru",
        "controlled_examples_en",
        "input_state_schema",
        "preconditions",
        "postconditions",
        "supported_languages",
    }
    row = dict(value)
    for name in tuple_fields:
        if not isinstance(row[name], list) or any(
            not isinstance(item, str) for item in row[name]
        ):
            raise TypeError(f"{name} must be a string array")
        row[name] = tuple(row[name])
    for name in ("effect_schema", "provenance"):
        if not isinstance(row[name], dict):
            raise TypeError(f"{name} must be an object")
    for name in (
        "skill_id",
        "rule_id",
        "rule_semantic_hash",
        "specification_hash",
        "installed_receipt_hash",
        "canonical_name_ru",
        "canonical_name_en",
        "effect_summary",
        "semantic_family",
        "created_at",
        "updated_at",
    ):
        if not isinstance(row[name], str) or not row[name]:
            raise TypeError(f"{name} must be a non-empty string")
    for name in (
        "rule_semantic_hash",
        "specification_hash",
        "installed_receipt_hash",
    ):
        if _SHA256.fullmatch(row[name]) is None:
            raise ValueError(f"{name} must be SHA-256")
    if not isinstance(row["active"], bool) or not isinstance(row["deprecated"], bool):
        raise TypeError("active/deprecated must be bool")
    if row["active"] == row["deprecated"]:
        raise ValueError("active and deprecated must be opposite states")
    for name in ("rule_version", "schema_version"):
        if (
            isinstance(row[name], bool)
            or not isinstance(row[name], int)
            or row[name] < 1
        ):
            raise TypeError(f"{name} must be a positive integer")
    if row["schema_version"] != STAGE2_SCHEMA_VERSION:
        raise ValueError("unsupported SkillRecord schema")
    _validate_timestamp(row["created_at"], "created_at")
    _validate_timestamp(row["updated_at"], "updated_at")
    return SkillRecord(**row)


def _validate_timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include timezone")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
