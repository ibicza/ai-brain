"""Fail-closed persistent-state mutation audit for Java production."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage3.domains.registry import InstalledDomainRegistry


@dataclass(frozen=True)
class JavaProductionStateAuditReport:
    fact_memory_write_attempts: int
    rule_memory_write_attempts: int
    skill_registry_write_attempts: int
    provider_registry_mutation_attempts: int
    domain_registry_mutation_attempts: int
    report_hash: str


class EnforcedJavaProductionStateAudit:
    """Reject writes to durable cognitive or domain authority during production.

    Provider and capability registries are immutable value objects: constructing or
    verifying one is not a mutation.  Their mutation denominator is therefore zero
    by architecture.  Domain-registry creation and every mutating operation are
    guarded until the caller exits this context and performs an explicit install.
    """

    _FACT_METHODS = (
        "initialize",
        "add_entity",
        "add_entity_alias",
        "add_predicate",
        "add_source",
        "add_evidence",
        "commit_proposal",
        "set_source_status",
    )
    _RULE_METHODS = ("add", "save")
    _SKILL_METHODS = ("update_skill_metadata", "save")
    _DOMAIN_METHODS = (
        "initialize",
        "install",
        "deprecate",
        "uninstall",
        "restore",
    )

    def __init__(self) -> None:
        self._counts = {
            "fact": 0,
            "rule": 0,
            "skill": 0,
            "domain": 0,
        }
        self._originals: list[tuple[type, str, object]] = []

    def __enter__(self):
        self._patch(FactMemory, self._FACT_METHODS, "fact")
        self._patch(RuleMemory, self._RULE_METHODS, "rule")
        self._patch(SkillRegistry, self._SKILL_METHODS, "skill")
        self._patch(InstalledDomainRegistry, self._DOMAIN_METHODS, "domain")
        return self

    def __exit__(self, *_args):
        for owner, name, original in reversed(self._originals):
            setattr(owner, name, original)
        self._originals.clear()

    def _patch(self, owner: type, names: tuple[str, ...], category: str) -> None:
        for name in names:
            original = owner.__dict__[name]
            self._originals.append((owner, name, original))

            def blocked(*_args, _category=category, _name=name, **_kwargs):
                self._counts[_category] += 1
                raise PermissionError(
                    f"{owner.__name__}.{_name} is forbidden during Java production"
                )

            if isinstance(original, classmethod):
                setattr(owner, name, classmethod(blocked))
            elif isinstance(original, staticmethod):
                setattr(owner, name, staticmethod(blocked))
            else:
                setattr(owner, name, blocked)

    def report(self) -> JavaProductionStateAuditReport:
        body = {
            "fact_memory_write_attempts": self._counts["fact"],
            "rule_memory_write_attempts": self._counts["rule"],
            "skill_registry_write_attempts": self._counts["skill"],
            "provider_registry_mutation_attempts": 0,
            "domain_registry_mutation_attempts": self._counts["domain"],
        }
        return JavaProductionStateAuditReport(**body, report_hash=content_hash(body))
