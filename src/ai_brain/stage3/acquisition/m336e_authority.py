"""Exact M-33.6e user authority root over the unchanged source-use semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336d_authority import (
    AuthorityPolicy,
    AuthorityRoot,
)
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)

M336E_AUTHORITY_ID = "M336E_USER_AUTHORITY_V1"
M336E_AUTHORITY_POLICY_VERSION = "m336e.authority.v1"
M336E_AUTHORITY_STATEMENT_SHA256 = (
    "f5d12c85ce1cb2a9b11a76bc4de229be0dc42c0b91ca99234325e7eb44305e77"
)
_FIELDS = (
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
class M336ESourceAuthorizationBinding:
    f20_sha: str
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
class M336EDerivedSourceAuthorizationReceipt:
    authority_root_hash: str
    authority_policy_id: str
    authority_policy_version: str
    f20_sha: str
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
    def _issued(cls, token, values):
        if token is not _RECEIPT_TOKEN:
            raise TypeError("M-33.6e authorization receipts are registry-issued only")
        result = object.__new__(cls)
        for name, value in values.items():
            object.__setattr__(result, name, value)
        return result


class M336EAuthorityRootRegistry:
    """Capability registry backed solely by the exact M-33.6e authority root."""

    _instances: ClassVar[set[int]] = set()

    def __init__(self, token, root: AuthorityRoot) -> None:
        if token is not _REGISTRY_TOKEN:
            raise TypeError("M-33.6e authority registry requires its frozen loader")
        self._root = root
        self._issued = {}
        self._instances.add(id(self))

    @property
    def root(self) -> AuthorityRoot:
        return self._root

    def issue(
        self,
        binding: M336ESourceAuthorizationBinding,
        *,
        source_use_scopes: tuple[SourceUseScope, ...] | None = None,
        publication_targets: tuple[PublicationTarget, ...] | None = None,
        parent: M336EDerivedSourceAuthorizationReceipt | None = None,
    ) -> M336EDerivedSourceAuthorizationReceipt:
        _verify_binding(binding)
        policy = self._root.policy
        if parent is not None:
            self.verify(parent, expected_binding=binding)
        parent_scopes = (
            parent.permitted_source_use_scopes if parent else policy.source_use
        )
        parent_targets = (
            parent.permitted_publication_targets if parent else policy.publication_allow
        )
        scopes = _ordered_subsequence(
            source_use_scopes if source_use_scopes is not None else parent_scopes,
            SourceUseScope,
            parent_scopes,
            "source-use scopes",
        )
        targets = _ordered_subsequence(
            publication_targets if publication_targets is not None else parent_targets,
            PublicationTarget,
            parent_targets,
            "publication targets",
        )
        if set(targets) & set(policy.publication_deny):
            raise ValueError("M-33.6e receipt inserted a denied publication target")
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
        receipt = M336EDerivedSourceAuthorizationReceipt._issued(
            _RECEIPT_TOKEN, {**body, "receipt_hash": content_hash(body)}
        )
        self._issued[receipt.receipt_hash] = receipt
        return receipt

    def verify(
        self,
        receipt: M336EDerivedSourceAuthorizationReceipt,
        *,
        expected_binding: M336ESourceAuthorizationBinding | None = None,
        parent: M336EDerivedSourceAuthorizationReceipt | None = None,
    ) -> None:
        if id(self) not in self._instances:
            raise ValueError("M-33.6e authority registry capability is invalid")
        if not isinstance(receipt, M336EDerivedSourceAuthorizationReceipt):
            raise TypeError("M-33.6e authorization receipt must be typed")
        if (
            expected_binding is None
            and self._issued.get(receipt.receipt_hash) is not receipt
        ):
            raise ValueError(
                "portable M-33.6e receipt verification requires an exact binding"
            )
        body = asdict(receipt)
        claimed = body.pop("receipt_hash")
        policy = self._root.policy
        if (
            content_hash(body) != claimed
            or receipt.authority_root_hash != self._root.root_hash
            or receipt.authority_policy_id != policy.policy_id
            or receipt.authority_policy_version != policy.policy_version
        ):
            raise ValueError("M-33.6e authorization receipt/root hash mismatch")
        if (
            expected_binding is not None
            and _binding_from_receipt(receipt) != expected_binding
        ):
            raise ValueError("receipt source, run, vault, or F20 binding mismatch")
        if (
            set(receipt.permitted_source_use_scopes) - set(policy.source_use)
            or set(receipt.permitted_publication_targets)
            - set(policy.publication_allow)
            or set(receipt.permitted_publication_targets) & set(policy.publication_deny)
        ):
            raise ValueError("M-33.6e authorization receipt widened authority")
        if receipt.parent_receipt_hash is not None:
            if parent is None or parent.receipt_hash != receipt.parent_receipt_hash:
                raise ValueError("M-33.6e receipt parent is absent or mismatched")
            self.verify(parent, expected_binding=expected_binding)
            if not set(receipt.permitted_source_use_scopes).issubset(
                parent.permitted_source_use_scopes
            ) or not set(receipt.permitted_publication_targets).issubset(
                parent.permitted_publication_targets
            ):
                raise ValueError("M-33.6e child receipt widened parent authority")


def load_m336e_authority_registry(
    statement_path: Path, *, expected_statement_sha256: str
) -> M336EAuthorityRootRegistry:
    """Load only the exact F20 authority statement and no historical alias."""

    if expected_statement_sha256 != M336E_AUTHORITY_STATEMENT_SHA256:
        raise ValueError("authority root is not the sole frozen M-33.6e root")
    raw = statement_path.resolve(strict=True).read_bytes()
    if bytes_hash(raw) != expected_statement_sha256:
        raise ValueError("M-33.6e authority statement byte hash differs")
    policy = _parse_exact_policy(raw)
    body = {
        "authority_id": M336E_AUTHORITY_ID,
        "statement_sha256": expected_statement_sha256,
        "statement_size": len(raw),
        "policy": policy,
    }
    root = AuthorityRoot(**body, root_hash=content_hash(body))
    return M336EAuthorityRootRegistry(_REGISTRY_TOKEN, root)


def m336e_receipt_public_dict(
    receipt: M336EDerivedSourceAuthorizationReceipt,
) -> dict:
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


def m336e_receipt_from_dict(value: dict) -> M336EDerivedSourceAuthorizationReceipt:
    """Load a receipt for cross-process verification without widening authority."""

    expected = {
        item.name
        for item in M336EDerivedSourceAuthorizationReceipt.__dataclass_fields__.values()
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("M-33.6e authorization receipt fields differ")
    converted = {
        **value,
        "permitted_source_use_scopes": tuple(
            SourceUseScope(item) for item in value["permitted_source_use_scopes"]
        ),
        "permitted_publication_targets": tuple(
            PublicationTarget(item) for item in value["permitted_publication_targets"]
        ),
        "denied_publication_targets": tuple(
            PublicationTarget(item) for item in value["denied_publication_targets"]
        ),
    }
    return M336EDerivedSourceAuthorizationReceipt._issued(_RECEIPT_TOKEN, converted)


def _parse_exact_policy(raw: bytes) -> AuthorityPolicy:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("M-33.6e authority statement is not strict UTF-8") from exc
    if "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
        raise ValueError("M-33.6e authority statement must use exact LF framing")
    lines = text[:-1].split("\n")
    if len(lines) != len(_FIELDS) + 1 or lines[0] != M336E_AUTHORITY_ID:
        raise ValueError("M-33.6e authority header or field count differs")
    parsed = {}
    for expected, line in zip(_FIELDS, lines[1:], strict=True):
        name, separator, value = line.partition("=")
        if separator != "=" or name != expected or not value:
            raise ValueError("M-33.6e authority field order/value differs")
        parsed[name] = value
    scopes = _parse_csv(parsed["source_use"], SourceUseScope, "source_use")
    allowed = _parse_csv(
        parsed["publication_allow"], PublicationTarget, "publication_allow"
    )
    denied = _parse_csv(
        parsed["publication_deny"], PublicationTarget, "publication_deny"
    )
    if set(allowed) & set(denied):
        raise ValueError("M-33.6e publication allow/deny overlap")
    if (
        parsed["raw_storage"] != "LOCAL_SEALED_VAULT_ONLY"
        or parsed["authority_may_narrow"] != "true"
        or parsed["authority_may_widen"] != "false"
    ):
        raise ValueError("M-33.6e authority storage/narrowing policy differs")
    body = {
        "policy_id": M336E_AUTHORITY_ID,
        "policy_version": M336E_AUTHORITY_POLICY_VERSION,
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


def _ordered_subsequence(values, enum_type, parent_order, label):
    result = tuple(enum_type(item) for item in values)
    parent = tuple(parent_order)
    if (
        not result
        or len(result) != len(set(result))
        or not set(result).issubset(parent)
        or result != tuple(item for item in parent if item in result)
    ):
        raise ValueError(f"{label} must be an ordered unique parent subset")
    return result


def _verify_binding(binding: M336ESourceAuthorizationBinding) -> None:
    if not isinstance(binding, M336ESourceAuthorizationBinding):
        raise TypeError("M-33.6e source authorization binding must be typed")
    for name, value in asdict(binding).items():
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(f"invalid M-33.6e authorization binding field: {name}")
    for name in (
        "source_jar_sha256",
        "pom_sha256",
        "scm_archive_sha256",
        "source_tree_hash",
        "local_vault_manifest_hash",
    ):
        value = getattr(binding, name)
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"invalid M-33.6e SHA-256 binding: {name}")
    if len(binding.f20_sha) != 40 or any(
        char not in "0123456789abcdef" for char in binding.f20_sha
    ):
        raise ValueError("invalid M-33.6e F20 SHA")
    if len(binding.immutable_scm_commit) != 40 or any(
        char not in "0123456789abcdef" for char in binding.immutable_scm_commit
    ):
        raise ValueError("invalid M-33.6e immutable SCM commit")


def _binding_from_receipt(
    receipt: M336EDerivedSourceAuthorizationReceipt,
) -> M336ESourceAuthorizationBinding:
    return M336ESourceAuthorizationBinding(
        **{
            name: getattr(receipt, name)
            for name in M336ESourceAuthorizationBinding.__dataclass_fields__
        }
    )
