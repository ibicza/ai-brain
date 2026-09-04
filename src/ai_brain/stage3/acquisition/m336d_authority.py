"""Frozen authority roots and non-widening derived source authorizations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)

_ROOT_HEADER = "M336D_USER_AUTHORITY_V1"
M336D_AUTHORITY_STATEMENT_SHA256 = (
    "87839e541c1e62ad4311ee20d2a3249271155aca79b8ba0d36b7563d4ce31806"
)
_ROOT_FIELDS = (
    "source_use",
    "publication_allow",
    "publication_deny",
    "raw_storage",
    "authority_may_narrow",
    "authority_may_widen",
)
_REGISTRY_TOKEN = object()
_RECEIPT_TOKEN = object()


@dataclass(frozen=True)
class AuthorityPolicy:
    policy_id: str
    policy_version: str
    source_use: tuple[SourceUseScope, ...]
    publication_allow: tuple[PublicationTarget, ...]
    publication_deny: tuple[PublicationTarget, ...]
    raw_storage: str
    authority_may_narrow: bool
    authority_may_widen: bool
    policy_hash: str


@dataclass(frozen=True)
class AuthorityRoot:
    authority_id: str
    statement_sha256: str
    statement_size: int
    policy: AuthorityPolicy
    root_hash: str


@dataclass(frozen=True)
class SourceAuthorizationBinding:
    f19_sha: str
    acquisition_run_id: str
    candidate_family_id: str
    maven_coordinate: str
    source_repository_url: str
    source_jar_sha256: str
    pom_sha256: str
    immutable_scm_commit: str
    scm_archive_sha256: str
    source_tree_hash: str
    local_vault_manifest_hash: str


@dataclass(frozen=True, init=False)
class DerivedSourceAuthorizationReceipt:
    authority_root_hash: str
    authority_policy_id: str
    authority_policy_version: str
    f19_sha: str
    acquisition_run_id: str
    candidate_family_id: str
    maven_coordinate: str
    source_repository_url: str
    source_jar_sha256: str
    pom_sha256: str
    immutable_scm_commit: str
    scm_archive_sha256: str
    source_tree_hash: str
    local_vault_manifest_hash: str
    permitted_source_use_scopes: tuple[SourceUseScope, ...]
    permitted_publication_targets: tuple[PublicationTarget, ...]
    denied_publication_targets: tuple[PublicationTarget, ...]
    parent_receipt_hash: str | None
    receipt_hash: str

    @classmethod
    def _issued(cls, token: object, values: dict) -> DerivedSourceAuthorizationReceipt:
        if token is not _RECEIPT_TOKEN:
            raise TypeError("derived authorization receipts are registry-issued only")
        value = object.__new__(cls)
        for name, item in values.items():
            object.__setattr__(value, name, item)
        return value


class AuthorityRootRegistry:
    """Registry capability backed by one exact, externally supplied root."""

    _instances: ClassVar[set[int]] = set()

    def __init__(self, token: object, root: AuthorityRoot) -> None:
        if token is not _REGISTRY_TOKEN:
            raise TypeError("authority registries must be loaded from a frozen root")
        self._root = root
        self._issued: dict[str, DerivedSourceAuthorizationReceipt] = {}
        self._instances.add(id(self))

    @property
    def root(self) -> AuthorityRoot:
        return self._root

    @classmethod
    def _load_pinned(
        cls, statement: bytes, *, expected_statement_sha256: str
    ) -> AuthorityRootRegistry:
        if expected_statement_sha256 != M336D_AUTHORITY_STATEMENT_SHA256:
            raise ValueError("authority root is not the sole frozen M-33.6d root")
        if bytes_hash(statement) != expected_statement_sha256:
            raise ValueError("authority statement hash does not match frozen root")
        policy = _parse_policy(statement)
        root_body = {
            "authority_id": _ROOT_HEADER,
            "statement_sha256": expected_statement_sha256,
            "statement_size": len(statement),
            "policy": policy,
        }
        root = AuthorityRoot(**root_body, root_hash=content_hash(root_body))
        return cls(_REGISTRY_TOKEN, root)

    def issue(
        self,
        binding: SourceAuthorizationBinding,
        *,
        source_use_scopes: tuple[SourceUseScope, ...] | None = None,
        publication_targets: tuple[PublicationTarget, ...] | None = None,
        parent: DerivedSourceAuthorizationReceipt | None = None,
    ) -> DerivedSourceAuthorizationReceipt:
        _verify_binding(binding)
        policy = self._root.policy
        parent_scopes = (
            parent.permitted_source_use_scopes if parent else policy.source_use
        )
        parent_targets = (
            parent.permitted_publication_targets if parent else policy.publication_allow
        )
        if parent is not None:
            self.verify(parent)
            if _binding_from_receipt(parent) != binding:
                raise ValueError("parent receipt belongs to another source binding")
        scopes = _ordered_unique_subsequence(
            source_use_scopes if source_use_scopes is not None else parent_scopes,
            SourceUseScope,
            "source-use scopes",
            parent_scopes,
        )
        targets = _ordered_unique_subsequence(
            publication_targets if publication_targets is not None else parent_targets,
            PublicationTarget,
            "publication targets",
            parent_targets,
        )
        if not set(scopes).issubset(parent_scopes):
            raise ValueError("derived authorization widened source-use scope")
        if not set(targets).issubset(parent_targets):
            raise ValueError("derived authorization widened publication scope")
        if set(targets) & set(policy.publication_deny):
            raise ValueError("derived authorization inserted a denied target")
        body = {
            "authority_root_hash": self._root.root_hash,
            "authority_policy_id": policy.policy_id,
            "authority_policy_version": policy.policy_version,
            **asdict(binding),
            "permitted_source_use_scopes": scopes,
            "permitted_publication_targets": targets,
            "denied_publication_targets": policy.publication_deny,
            "parent_receipt_hash": parent.receipt_hash if parent else None,
        }
        values = {**body, "receipt_hash": content_hash(body)}
        receipt = DerivedSourceAuthorizationReceipt._issued(_RECEIPT_TOKEN, values)
        self._issued[receipt.receipt_hash] = receipt
        return receipt

    def verify(
        self,
        receipt: DerivedSourceAuthorizationReceipt,
        *,
        expected_binding: SourceAuthorizationBinding | None = None,
        parent: DerivedSourceAuthorizationReceipt | None = None,
    ) -> None:
        if id(self) not in self._instances:
            raise ValueError("authority registry capability is invalid")
        if not isinstance(receipt, DerivedSourceAuthorizationReceipt):
            raise TypeError("derived authorization receipt must be typed")
        issued = self._issued.get(receipt.receipt_hash)
        if issued is None or issued is not receipt:
            raise ValueError("receipt was not issued by this authority registry")
        body = asdict(receipt)
        claimed = body.pop("receipt_hash")
        if content_hash(body) != claimed:
            raise ValueError("derived authorization receipt hash mismatch")
        if receipt.authority_root_hash != self._root.root_hash:
            raise ValueError("receipt authority root mismatch")
        policy = self._root.policy
        if (
            receipt.authority_policy_id != policy.policy_id
            or receipt.authority_policy_version != policy.policy_version
        ):
            raise ValueError("receipt authority policy mismatch")
        if (
            expected_binding is not None
            and _binding_from_receipt(receipt) != expected_binding
        ):
            raise ValueError("receipt source, run, vault, or freeze binding mismatch")
        if set(receipt.permitted_source_use_scopes) - set(policy.source_use):
            raise ValueError("receipt contains widened source-use scope")
        if set(receipt.permitted_publication_targets) - set(policy.publication_allow):
            raise ValueError("receipt contains widened publication target")
        if set(receipt.permitted_publication_targets) & set(policy.publication_deny):
            raise ValueError("receipt contains denied publication target")
        if receipt.parent_receipt_hash is not None:
            if parent is None or parent.receipt_hash != receipt.parent_receipt_hash:
                raise ValueError("receipt parent is absent or mismatched")
            self.verify(parent, expected_binding=expected_binding)
            if not set(receipt.permitted_source_use_scopes).issubset(
                parent.permitted_source_use_scopes
            ):
                raise ValueError("child receipt widened parent source-use scope")
            if not set(receipt.permitted_publication_targets).issubset(
                parent.permitted_publication_targets
            ):
                raise ValueError("child receipt widened parent publication scope")


def load_pinned_authority_registry_for_development(
    statement_path: Path, *, expected_statement_sha256: str
) -> AuthorityRootRegistry:
    """R19 disclosed-only loader; F19 replaces its call site with frozen config."""

    raw = statement_path.resolve(strict=True).read_bytes()
    return AuthorityRootRegistry._load_pinned(
        raw, expected_statement_sha256=expected_statement_sha256
    )


def receipt_public_dict(receipt: DerivedSourceAuthorizationReceipt) -> dict:
    value = asdict(receipt)
    value["permitted_source_use_scopes"] = tuple(
        item.value for item in receipt.permitted_source_use_scopes
    )
    value["permitted_publication_targets"] = tuple(
        item.value for item in receipt.permitted_publication_targets
    )
    value["denied_publication_targets"] = tuple(
        item.value for item in receipt.denied_publication_targets
    )
    return value


def _parse_policy(raw: bytes) -> AuthorityPolicy:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("authority statement is not strict UTF-8") from exc
    if "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
        raise ValueError("authority statement must use exact LF framing")
    lines = text[:-1].split("\n")
    if len(lines) != 1 + len(_ROOT_FIELDS) or lines[0] != _ROOT_HEADER:
        raise ValueError("authority statement header or field count mismatch")
    parsed: dict[str, str] = {}
    for expected, line in zip(_ROOT_FIELDS, lines[1:], strict=True):
        name, separator, value = line.partition("=")
        if separator != "=" or name != expected or not value:
            raise ValueError("authority statement field order or value mismatch")
        parsed[name] = value
    scopes = _parse_csv(parsed["source_use"], SourceUseScope, "source_use")
    allowed = _parse_csv(
        parsed["publication_allow"], PublicationTarget, "publication_allow"
    )
    denied = _parse_csv(
        parsed["publication_deny"], PublicationTarget, "publication_deny"
    )
    if set(allowed) & set(denied):
        raise ValueError("authority publication allow/deny overlap")
    if parsed["raw_storage"] != "LOCAL_SEALED_VAULT_ONLY":
        raise ValueError("authority raw-storage policy mismatch")
    if (
        parsed["authority_may_narrow"] != "true"
        or parsed["authority_may_widen"] != "false"
    ):
        raise ValueError("authority narrowing/widening policy mismatch")
    body = {
        "policy_id": _ROOT_HEADER,
        "policy_version": "m336d.authority.v1",
        "source_use": scopes,
        "publication_allow": allowed,
        "publication_deny": denied,
        "raw_storage": parsed["raw_storage"],
        "authority_may_narrow": True,
        "authority_may_widen": False,
    }
    return AuthorityPolicy(**body, policy_hash=content_hash(body))


def _parse_csv(value: str, enum_type, label: str):
    raw = value.split(",")
    if any(not item or item.strip() != item for item in raw) or len(raw) != len(
        set(raw)
    ):
        raise ValueError(f"{label} must be ordered, unique, and whitespace-free")
    return tuple(enum_type(item) for item in raw)


def _ordered_unique_subsequence(values, enum_type, label: str, parent_order):
    result = tuple(enum_type(item) for item in values)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{label} must be non-empty and unique")
    parent = tuple(parent_order)
    if not set(result).issubset(parent):
        raise ValueError(f"{label} contains a value absent from its parent")
    canonical = tuple(item for item in parent if item in result)
    if result != canonical:
        raise ValueError(f"{label} must preserve frozen parent order")
    return result


def _verify_binding(binding: SourceAuthorizationBinding) -> None:
    if not isinstance(binding, SourceAuthorizationBinding):
        raise TypeError("source authorization binding must be typed")
    for name, value in asdict(binding).items():
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(f"invalid source authorization binding field: {name}")
    for name in (
        "source_jar_sha256",
        "pom_sha256",
        "scm_archive_sha256",
        "source_tree_hash",
        "local_vault_manifest_hash",
    ):
        value = getattr(binding, name)
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"invalid SHA-256 binding: {name}")
    if len(binding.f19_sha) != 40 or any(
        char not in "0123456789abcdef" for char in binding.f19_sha
    ):
        raise ValueError("invalid F19 Git SHA")
    if len(binding.immutable_scm_commit) != 40 or any(
        char not in "0123456789abcdef" for char in binding.immutable_scm_commit
    ):
        raise ValueError("invalid immutable SCM commit")


def _binding_from_receipt(
    receipt: DerivedSourceAuthorizationReceipt,
) -> SourceAuthorizationBinding:
    return SourceAuthorizationBinding(
        **{
            name: getattr(receipt, name)
            for name in SourceAuthorizationBinding.__dataclass_fields__
        }
    )
