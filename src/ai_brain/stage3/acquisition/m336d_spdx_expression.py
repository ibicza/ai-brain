"""Typed SPDX expressions and exact source-path applicability scopes."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import content_hash

_TOKEN = re.compile(
    r"\s*(\(|\)|AND\b|OR\b|WITH\b|[A-Za-z0-9][A-Za-z0-9.+-]*)",
    re.ASCII,
)


@dataclass(frozen=True)
class SPDXExpression:
    def canonical(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class SPDXLicenseId(SPDXExpression):
    license_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.license_id)

    def canonical(self) -> str:
        return self.license_id


@dataclass(frozen=True)
class SPDXWithException(SPDXExpression):
    license: SPDXLicenseId
    exception: SPDXLicenseId

    def canonical(self) -> str:
        return f"{self.license.canonical()} WITH {self.exception.canonical()}"


@dataclass(frozen=True)
class SPDXAndExpression(SPDXExpression):
    left: SPDXExpression
    right: SPDXExpression

    def canonical(self) -> str:
        return f"({_canonical_child(self.left)}) AND ({_canonical_child(self.right)})"


@dataclass(frozen=True)
class SPDXOrExpression(SPDXExpression):
    left: SPDXExpression
    right: SPDXExpression

    def canonical(self) -> str:
        return f"({_canonical_child(self.left)}) OR ({_canonical_child(self.right)})"


class LicenseScopeKind(StrEnum):
    PROJECT_ROOT = "PROJECT_ROOT"
    MODULE_PATH = "MODULE_PATH"
    SOURCE_PATH_PREFIX = "SOURCE_PATH_PREFIX"
    FILE_OVERRIDE = "FILE_OVERRIDE"


@dataclass(frozen=True)
class LicenseApplicabilityScope:
    kind: LicenseScopeKind
    path: str
    scope_hash: str

    @classmethod
    def build(cls, kind: LicenseScopeKind, path: str = "."):
        kind = LicenseScopeKind(kind)
        normalized = _canonical_relative_path(path, allow_root=True)
        if kind is LicenseScopeKind.PROJECT_ROOT and normalized != ".":
            raise ValueError("project-root license scope must use '.'")
        if kind is not LicenseScopeKind.PROJECT_ROOT and normalized == ".":
            raise ValueError("non-root license scope requires a relative path")
        body = {"kind": kind, "path": normalized}
        return cls(**body, scope_hash=content_hash(body))

    def applies_to(self, source_path: str) -> bool:
        source = _canonical_relative_path(source_path, allow_root=False)
        if self.kind is LicenseScopeKind.PROJECT_ROOT:
            return True
        if self.kind is LicenseScopeKind.FILE_OVERRIDE:
            return source == self.path
        return source == self.path or source.startswith(f"{self.path}/")

    @property
    def specificity(self) -> tuple[int, int]:
        rank = {
            LicenseScopeKind.PROJECT_ROOT: 0,
            LicenseScopeKind.MODULE_PATH: 1,
            LicenseScopeKind.SOURCE_PATH_PREFIX: 2,
            LicenseScopeKind.FILE_OVERRIDE: 3,
        }[self.kind]
        return rank, len(PurePosixPath(self.path).parts)


class ScopedLicenseStatus(StrEnum):
    RESOLVED = "RESOLVED"
    REVIEW_REQUIRED_UNSPECIFIED_MULTI_LICENSE = (
        "REVIEW_REQUIRED_UNSPECIFIED_MULTI_LICENSE"
    )
    REVIEW_REQUIRED_AMBIGUOUS_SCOPE = "REVIEW_REQUIRED_AMBIGUOUS_SCOPE"
    TRUE_INCOMPATIBLE_SCOPED_CONFLICT = "TRUE_INCOMPATIBLE_SCOPED_CONFLICT"


@dataclass(frozen=True)
class ScopedLicenseEvidence:
    expression: SPDXExpression | None
    scope: LicenseApplicabilityScope
    evidence_receipt_hashes: tuple[str, ...]
    status: ScopedLicenseStatus
    reason: str
    receipt_hash: str

    @classmethod
    def build(
        cls,
        *,
        expression: SPDXExpression | None,
        scope: LicenseApplicabilityScope,
        evidence_receipt_hashes: tuple[str, ...],
        status: ScopedLicenseStatus,
        reason: str,
    ) -> ScopedLicenseEvidence:
        hashes = tuple(evidence_receipt_hashes)
        if not hashes or hashes != tuple(sorted(set(hashes))):
            raise ValueError("scoped license evidence hashes must be sorted and unique")
        for value in hashes:
            if len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError("invalid scoped license evidence hash")
        status = ScopedLicenseStatus(status)
        if status is ScopedLicenseStatus.RESOLVED and expression is None:
            raise ValueError("resolved scoped license evidence needs an expression")
        body = {
            "expression": expression.canonical() if expression else None,
            "scope": scope,
            "evidence_receipt_hashes": hashes,
            "status": status,
            "reason": reason,
        }
        return cls(
            expression=expression,
            scope=scope,
            evidence_receipt_hashes=hashes,
            status=status,
            reason=reason,
            receipt_hash=content_hash(body),
        )


@dataclass(frozen=True)
class ApplicableLicenseDecision:
    source_path: str
    expression: SPDXExpression | None
    status: ScopedLicenseStatus
    evidence_hashes: tuple[str, ...]
    decision_hash: str


def parse_spdx_expression(value: str) -> SPDXExpression:
    if (
        not isinstance(value, str)
        or not value
        or unicodedata.normalize("NFC", value) != value
    ):
        raise ValueError("SPDX expression must be non-empty NFC text")
    tokens = []
    offset = 0
    while offset < len(value):
        match = _TOKEN.match(value, offset)
        if match is None:
            raise ValueError(f"invalid SPDX expression at offset {offset}")
        tokens.append(match.group(1))
        offset = match.end()
    parser = _Parser(tuple(tokens))
    result = parser.parse_or()
    if parser.position != len(tokens):
        raise ValueError("unexpected SPDX expression token")
    return result


def pom_license_evidence(
    expressions: tuple[str, ...], *, evidence_hash: str
) -> ScopedLicenseEvidence:
    scope = LicenseApplicabilityScope.build(LicenseScopeKind.PROJECT_ROOT)
    values = tuple(dict.fromkeys(expressions))
    if len(values) != 1:
        return ScopedLicenseEvidence.build(
            expression=None,
            scope=scope,
            evidence_receipt_hashes=(evidence_hash,),
            status=ScopedLicenseStatus.REVIEW_REQUIRED_UNSPECIFIED_MULTI_LICENSE,
            reason="POM_MULTI_LICENSE_RELATIONSHIP_NOT_MECHANICALLY_ESTABLISHED",
        )
    return ScopedLicenseEvidence.build(
        expression=parse_spdx_expression(values[0]),
        scope=scope,
        evidence_receipt_hashes=(evidence_hash,),
        status=ScopedLicenseStatus.RESOLVED,
        reason="SINGLE_POM_SPDX_EXPRESSION",
    )


def resolve_scoped_license(
    source_path: str, evidence: tuple[ScopedLicenseEvidence, ...]
) -> ApplicableLicenseDecision:
    source = _canonical_relative_path(source_path, allow_root=False)
    applicable = tuple(item for item in evidence if item.scope.applies_to(source))
    if not applicable:
        status = ScopedLicenseStatus.REVIEW_REQUIRED_AMBIGUOUS_SCOPE
        expression = None
        hashes = ()
    else:
        specificity = max(item.scope.specificity for item in applicable)
        most_specific = tuple(
            item for item in applicable if item.scope.specificity == specificity
        )
        hashes = tuple(
            sorted(
                {
                    value
                    for item in most_specific
                    for value in item.evidence_receipt_hashes
                }
            )
        )
        if any(
            item.status is not ScopedLicenseStatus.RESOLVED for item in most_specific
        ):
            status = next(
                item.status
                for item in most_specific
                if item.status is not ScopedLicenseStatus.RESOLVED
            )
            expression = None
        else:
            expressions = {item.expression.canonical() for item in most_specific}
            if len(expressions) != 1:
                status = ScopedLicenseStatus.TRUE_INCOMPATIBLE_SCOPED_CONFLICT
                expression = None
            else:
                status = ScopedLicenseStatus.RESOLVED
                expression = most_specific[0].expression
    body = {
        "source_path": source,
        "expression": expression.canonical() if expression else None,
        "status": status,
        "evidence_hashes": hashes,
    }
    return ApplicableLicenseDecision(
        source_path=source,
        expression=expression,
        status=status,
        evidence_hashes=hashes,
        decision_hash=content_hash(body),
    )


class _Parser:
    def __init__(self, tokens: tuple[str, ...]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse_or(self) -> SPDXExpression:
        left = self.parse_and()
        while self._take("OR"):
            left = SPDXOrExpression(left, self.parse_and())
        return left

    def parse_and(self) -> SPDXExpression:
        left = self.parse_with()
        while self._take("AND"):
            left = SPDXAndExpression(left, self.parse_with())
        return left

    def parse_with(self) -> SPDXExpression:
        left = self.parse_primary()
        if self._take("WITH"):
            if not isinstance(left, SPDXLicenseId):
                raise ValueError("WITH left operand must be a license identifier")
            right = self.parse_primary()
            if not isinstance(right, SPDXLicenseId):
                raise ValueError("WITH right operand must be an exception identifier")
            return SPDXWithException(left, right)
        return left

    def parse_primary(self) -> SPDXExpression:
        if self._take("("):
            value = self.parse_or()
            if not self._take(")"):
                raise ValueError("missing SPDX expression closing parenthesis")
            return value
        if self.position >= len(self.tokens):
            raise ValueError("missing SPDX expression identifier")
        token = self.tokens[self.position]
        if token in {"AND", "OR", "WITH", ")"}:
            raise ValueError("unexpected SPDX expression operator")
        self.position += 1
        return SPDXLicenseId(token)

    def _take(self, token: str) -> bool:
        if self.position < len(self.tokens) and self.tokens[self.position] == token:
            self.position += 1
            return True
        return False


def _validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", value, re.ASCII):
        raise ValueError("invalid SPDX license or exception identifier")


def _canonical_child(value: SPDXExpression) -> str:
    return value.canonical()


def _canonical_relative_path(value: str, *, allow_root: bool) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("license scope path must be a non-empty POSIX path")
    if unicodedata.normalize("NFC", value) != value or re.match(r"^[A-Za-z]:", value):
        raise ValueError("license scope path is not canonical NFC relative text")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("license scope path escapes the source root")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        if allow_root:
            return "."
        raise ValueError("source path may not name the project root")
    if normalized.startswith("./") or "//" in value:
        raise ValueError("license scope path is not canonical")
    return normalized
