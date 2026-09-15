"""Canonical official acquisition binding for the M-33.6k.10 recovery route.

The objects in this module form a one-way hash graph:

candidate pool -> derived network authority -> official policy -> authorization
-> stage/ledger bindings -> final admission receipt.

No official value is seeded from a rehearsal policy or authorization.
"""

from __future__ import annotations

import ipaddress
import re
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileStatus,
)

M336K10_PROFILE_ID = "m336k8-final-v3"
M336K10_ACQUISITION_RUN_ID = "m336k8.final-java.global-acquisition.v3"
M336K11_PROFILE_ID = "m336k8-final-v4"
M336K11_ACQUISITION_RUN_ID = "m336k8.final-java.global-acquisition.v4"
M336K_OFFICIAL_ACQUISITION_PROFILE_IDS = frozenset(
    {M336K10_PROFILE_ID, M336K11_PROFILE_ID}
)
M336K_OFFICIAL_ACQUISITION_RUN_IDS = frozenset(
    {M336K10_ACQUISITION_RUN_ID, M336K11_ACQUISITION_RUN_ID}
)
M336K10_OFFICIAL_POOL_SEMANTIC_HASH = (
    "b48ee354dc710a6c0ac0ed2cfceb1385c0d12cc8efb6b8fbef00e8d2f6ab572e"
)
M336K10_OFFICIAL_POOL_BYTES_HASH = (
    "78cfb85fc59687186f0e420d410bf648816bce6ae2539acb445f8da74d77a0fa"
)
M336K10_REQUIRED_OFFICIAL_HOSTS = (
    "codeload.github.com",
    "github.com",
    "repo.maven.apache.org",
)
M336K10_EXECUTION_SCOPE_OFFICIAL = "OFFICIAL"
M336K10_EXECUTION_SCOPE_REHEARSAL = "REHEARSAL"
M336K10_EXECUTION_SCOPE_SHARED = "SHARED_POLICY"
M336K10_EXECUTION_SCOPE_HISTORICAL = "HISTORICAL_READ_ONLY"
M336K10_EXECUTION_SCOPES = frozenset(
    {
        M336K10_EXECUTION_SCOPE_OFFICIAL,
        M336K10_EXECUTION_SCOPE_REHEARSAL,
        M336K10_EXECUTION_SCOPE_SHARED,
        M336K10_EXECUTION_SCOPE_HISTORICAL,
    }
)
M336K10_MUTATION_CASES = (
    "official-pool-with-disposable-policy",
    "official-pool-with-fixture-hosts",
    "policy-pool-hash-wrong",
    "authorization-pool-hash-wrong",
    "provider-pool-binding-wrong",
    "policy-hosts-wrong",
    "authorization-hosts-wrong",
    "provider-hosts-wrong",
    "missing-official-host",
    "extra-official-host",
    "uppercase-host-variant",
    "url-host-changed",
    "http-url",
    "candidate-order-changed",
    "candidate-added",
    "candidate-removed",
    "candidate-policy-hash-changed",
    "v2-acquisition-run-id",
    "rehearsal-profile-in-official-policy",
    "rehearsal-scope-relabeled-official",
    "legacy-acquisition-policy-copied",
    "legacy-authorization-copied",
    "forged-pass-receipt",
    "validate-only-verifier-omitted",
    "controller-receipt-differs",
    "stage-request-binding-changed",
    "worker-provider-host-set-changed",
    "route-event-before-admission",
    "fixture-host-in-official-components",
    "wrong-pool-in-official-components",
)
M336K10_ACQUISITION_SEMANTIC_PREDICATES = (
    "acquisition_policy_hash",
    "policy_version",
    "acquisition_run_id",
    "candidate_pool_hash",
    "archive_policy_hash",
    "candidate_terminal_policy_hash",
    "global_continuation_policy_hash",
    "allowed_network_hosts",
    "authority_statement_hash",
    "disclosure_registry_manifest_hash",
    "acquisition_reservation_limit",
    "candidate_retry_limit",
    "candidate_replacement_limit",
    "pre_freeze_source_body_bytes",
    "selector_target_file_count",
    "maximum_selected_files_per_root",
    "minimum_selected_root_count",
    "construct_quotas",
    "selector_seed",
    "selector_version",
)

_HASH = re.compile(r"[0-9a-f]{64}")
_PURPOSES = frozenset(
    {
        "SOURCE_JAR",
        "SOURCE_SHA256_SIDECAR",
        "SOURCE_SIGNATURE",
        "POM",
        "POM_SHA256_SIDECAR",
        "POM_SIGNATURE",
        "SCM_REF",
        "SCM_ARCHIVE_REQUEST",
        "SCM_ARCHIVE_FINAL",
    }
)


def _is_hash(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _strict(value: dict[str, Any], cls: type, label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {item.name for item in fields(cls)}:
        raise M336K2ProtocolError(f"M336K10 {label} fields changed")
    return value


@dataclass(frozen=True)
class M336K10NetworkEndpointBinding:
    schema_version: int
    contract_role: str
    execution_scope: str
    candidate_ordinal: int
    family_id: str
    organization_id: str
    purpose: str
    normalized_url: str
    normalized_url_hash: str
    scheme: str
    hostname: str
    port: int
    endpoint_hash: str

    ROLE: ClassVar[str] = "M336K10_NETWORK_ENDPOINT_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("endpoint_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "endpoint_hash": self.endpoint_hash}

    def verify(self) -> None:
        parsed = urllib.parse.urlsplit(self.normalized_url)
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or type(self.candidate_ordinal) is not int
            or self.candidate_ordinal < 1
            or not self.family_id
            or not self.organization_id
            or self.purpose not in _PURPOSES
            or self.scheme != "https"
            or self.hostname not in M336K10_REQUIRED_OFFICIAL_HOSTS
            or self.hostname != self.hostname.lower()
            or self.port != 443
            or parsed.scheme != self.scheme
            or parsed.hostname != self.hostname
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or self.normalized_url_hash != content_hash(self.normalized_url)
            or self.endpoint_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 network endpoint is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "network endpoint"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10OfficialCandidatePoolBinding:
    schema_version: int
    contract_role: str
    execution_scope: str
    pool_semantic_hash: str
    pool_bytes_hash: str
    candidate_count: int
    organization_count: int
    maximum_candidates_per_organization: int
    ordered_candidate_identity_manifest_hash: str
    ordered_family_id_manifest_hash: str
    candidate_url_manifest_hash: str
    derived_network_authority_hash: str
    binding_hash: str

    ROLE: ClassVar[str] = "M336K10_OFFICIAL_CANDIDATE_POOL_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_hash": self.binding_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or self.pool_semantic_hash != M336K10_OFFICIAL_POOL_SEMANTIC_HASH
            or self.pool_bytes_hash != M336K10_OFFICIAL_POOL_BYTES_HASH
            or self.candidate_count != 96
            or self.organization_count != 64
            or self.maximum_candidates_per_organization != 2
            or any(not _is_hash(value) for value in hashes)
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError(
                "M336K10 official candidate-pool binding is invalid"
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "candidate-pool binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10NetworkAuthorityManifest:
    schema_version: int
    contract_role: str
    execution_scope: str
    endpoints: tuple[M336K10NetworkEndpointBinding, ...]
    allowed_network_hosts: tuple[str, ...]
    host_set_hash: str
    url_manifest_hash: str
    derived_network_authority_hash: str
    pool_binding_hash: str
    unknown_host_count: int
    non_https_endpoint_count: int
    host_normalization_collision_count: int
    fixture_host_occurrence_count: int
    manifest_hash: str

    ROLE: ClassVar[str] = "M336K10_OFFICIAL_NETWORK_AUTHORITY_MANIFEST"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "execution_scope": self.execution_scope,
            "endpoints": tuple(item.canonical_object() for item in self.endpoints),
            "allowed_network_hosts": self.allowed_network_hosts,
            "host_set_hash": self.host_set_hash,
            "url_manifest_hash": self.url_manifest_hash,
            "derived_network_authority_hash": self.derived_network_authority_hash,
            "pool_binding_hash": self.pool_binding_hash,
            "unknown_host_count": self.unknown_host_count,
            "non_https_endpoint_count": self.non_https_endpoint_count,
            "host_normalization_collision_count": self.host_normalization_collision_count,
            "fixture_host_occurrence_count": self.fixture_host_occurrence_count,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self) -> None:
        for endpoint in self.endpoints:
            endpoint.verify()
        ordering = tuple(
            sorted(
                self.endpoints,
                key=lambda item: (
                    item.candidate_ordinal,
                    item.purpose.encode("utf-8"),
                    item.normalized_url.encode("utf-8"),
                ),
            )
        )
        hosts = tuple(sorted({item.hostname for item in self.endpoints}))
        endpoint_hashes = tuple(item.endpoint_hash for item in self.endpoints)
        authority = content_hash(
            (
                hosts,
                tuple(
                    (
                        item.candidate_ordinal,
                        item.family_id,
                        item.purpose,
                        item.normalized_url,
                    )
                    for item in self.endpoints
                ),
            )
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or not self.endpoints
            or self.endpoints != ordering
            or hosts != self.allowed_network_hosts
            or hosts != M336K10_REQUIRED_OFFICIAL_HOSTS
            or self.host_set_hash != content_hash(hosts)
            or self.url_manifest_hash != content_hash(endpoint_hashes)
            or self.derived_network_authority_hash != authority
            or not _is_hash(self.pool_binding_hash)
            or self.unknown_host_count != 0
            or self.non_https_endpoint_count != 0
            or self.host_normalization_collision_count != 0
            or self.fixture_host_occurrence_count != 0
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 network authority manifest is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        data = _strict(value, cls, "network authority manifest")
        if (
            type(data["endpoints"]) is not list
            or type(data["allowed_network_hosts"]) is not list
        ):
            raise M336K2ProtocolError("M336K10 network authority collections changed")
        result = cls(
            **{
                **data,
                "endpoints": tuple(
                    M336K10NetworkEndpointBinding.from_dict(item)
                    for item in data["endpoints"]
                ),
                "allowed_network_hosts": tuple(data["allowed_network_hosts"]),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10SharedPolicyBinding:
    schema_version: int
    contract_role: str
    execution_scope: str
    archive_policy_hash: str
    candidate_terminal_policy_hash: str
    global_continuation_policy_hash: str
    authority_statement_hash: str
    disclosure_registry_manifest_hash: str
    selector_policy_hash: str
    binding_hash: str

    ROLE: ClassVar[str] = "M336K10_SHARED_ACQUISITION_POLICY_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_hash": self.binding_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_SHARED
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 shared policy binding is invalid")

    @classmethod
    def build(cls, **hashes: str) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": M336K10_EXECUTION_SCOPE_SHARED,
            **hashes,
        }
        result = cls(**body, binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "shared policy binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10OfficialAcquisitionPolicy:
    schema_version: int
    contract_role: str
    execution_scope: str
    policy_version: str
    acquisition_run_id: str
    candidate_pool_hash: str
    official_candidate_pool_binding_hash: str
    network_authority_manifest_hash: str
    derived_host_set_hash: str
    allowed_network_hosts: tuple[str, ...]
    archive_policy_hash: str
    candidate_terminal_policy_hash: str
    global_continuation_policy_hash: str
    authority_statement_hash: str
    disclosure_registry_manifest_hash: str
    shared_policy_binding_hash: str
    selector_target_file_count: int
    minimum_selected_root_count: int
    maximum_selected_files_per_root: int
    construct_quotas: tuple[tuple[str, int], ...]
    selector_seed: str
    selector_version: str
    acquisition_reservation_limit: int
    candidate_retry_limit: int
    candidate_replacement_limit: int
    pre_freeze_source_body_bytes: int
    acquisition_policy_hash: str

    ROLE: ClassVar[str] = "M336K10_OFFICIAL_ACQUISITION_POLICY"
    VERSION: ClassVar[str] = "m336k10.official-acquisition.v1"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("acquisition_policy_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "acquisition_policy_hash": self.acquisition_policy_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or self.policy_version != self.VERSION
            or self.acquisition_run_id not in M336K_OFFICIAL_ACQUISITION_RUN_IDS
            or self.allowed_network_hosts != M336K10_REQUIRED_OFFICIAL_HOSTS
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.selector_target_file_count != 180
            or self.minimum_selected_root_count < 3
            or self.maximum_selected_files_per_root <= 0
            or self.maximum_selected_files_per_root > 63
            or not self.construct_quotas
            or any(
                type(name) is not str
                or not name
                or type(count) is not int
                or count <= 0
                for name, count in self.construct_quotas
            )
            or type(self.selector_seed) is not str
            or not self.selector_seed
            or type(self.selector_version) is not str
            or not self.selector_version
            or self.acquisition_reservation_limit != 1
            or self.candidate_retry_limit != 0
            or self.candidate_replacement_limit != 0
            or self.pre_freeze_source_body_bytes != 0
            or self.acquisition_policy_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 official acquisition policy is invalid")

    @classmethod
    def build(
        cls,
        *,
        pool_binding: M336K10OfficialCandidatePoolBinding,
        network_authority: M336K10NetworkAuthorityManifest,
        profile: M336KOfficialRouteProfile,
        shared_policy: M336K10SharedPolicyBinding,
        selector_policy: dict[str, Any],
    ) -> Self:
        pool_binding.verify()
        network_authority.verify()
        shared_policy.verify()
        profile.verify()
        if (
            profile.profile_id not in M336K_OFFICIAL_ACQUISITION_PROFILE_IDS
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
            or profile.acquisition_run_id not in M336K_OFFICIAL_ACQUISITION_RUN_IDS
            or network_authority.pool_binding_hash != pool_binding.binding_hash
        ):
            raise M336K2ProtocolError(
                "M336K10 active profile acquisition binding changed"
            )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
            "policy_version": cls.VERSION,
            "acquisition_run_id": profile.acquisition_run_id,
            "candidate_pool_hash": pool_binding.pool_semantic_hash,
            "official_candidate_pool_binding_hash": pool_binding.binding_hash,
            "network_authority_manifest_hash": network_authority.manifest_hash,
            "derived_host_set_hash": network_authority.host_set_hash,
            "allowed_network_hosts": network_authority.allowed_network_hosts,
            "archive_policy_hash": shared_policy.archive_policy_hash,
            "candidate_terminal_policy_hash": shared_policy.candidate_terminal_policy_hash,
            "global_continuation_policy_hash": shared_policy.global_continuation_policy_hash,
            "authority_statement_hash": shared_policy.authority_statement_hash,
            "disclosure_registry_manifest_hash": shared_policy.disclosure_registry_manifest_hash,
            "shared_policy_binding_hash": shared_policy.binding_hash,
            "selector_target_file_count": selector_policy["target_file_count"],
            "minimum_selected_root_count": selector_policy["minimum_root_count"],
            "maximum_selected_files_per_root": selector_policy[
                "maximum_files_per_root"
            ],
            "construct_quotas": tuple(
                (str(name), int(count))
                for name, count in selector_policy["construct_quotas"]
            ),
            "selector_seed": selector_policy["selector_seed"],
            "selector_version": selector_policy["selector_version"],
            "acquisition_reservation_limit": 1,
            "candidate_retry_limit": 0,
            "candidate_replacement_limit": 0,
            "pre_freeze_source_body_bytes": 0,
        }
        result = cls(**body, acquisition_policy_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        data = _strict(value, cls, "official acquisition policy")
        if type(data["allowed_network_hosts"]) is not list or not isinstance(
            data["construct_quotas"], list
        ):
            raise M336K2ProtocolError("M336K10 acquisition policy collections changed")
        quotas = data["construct_quotas"]
        if any(
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            for item in quotas
        ):
            raise M336K2ProtocolError("M336K10 acquisition policy quotas changed")
        result = cls(
            **{
                **data,
                "allowed_network_hosts": tuple(data["allowed_network_hosts"]),
                "construct_quotas": tuple((name, count) for name, count in quotas),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10ProviderConfiguration:
    schema_version: int
    contract_role: str
    execution_scope: str
    official_candidate_pool_binding_hash: str
    network_authority_manifest_hash: str
    allowed_network_hosts: tuple[str, ...]
    maven_provider_hosts: tuple[str, ...]
    scm_provider_hosts: tuple[str, ...]
    maven_provider_source_hash: str
    scm_provider_source_hash: str
    configuration_hash: str

    ROLE: ClassVar[str] = "M336K10_OFFICIAL_PROVIDER_CONFIGURATION"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("configuration_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "configuration_hash": self.configuration_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or self.allowed_network_hosts != M336K10_REQUIRED_OFFICIAL_HOSTS
            or self.maven_provider_hosts != ("repo.maven.apache.org",)
            or self.scm_provider_hosts != ("codeload.github.com", "github.com")
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.configuration_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 provider configuration is invalid")

    @classmethod
    def build(
        cls,
        *,
        pool_binding: M336K10OfficialCandidatePoolBinding,
        network_authority: M336K10NetworkAuthorityManifest,
        maven_provider_source: bytes,
        scm_provider_source: bytes,
    ) -> Self:
        pool_binding.verify()
        network_authority.verify()
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
            "official_candidate_pool_binding_hash": pool_binding.binding_hash,
            "network_authority_manifest_hash": network_authority.manifest_hash,
            "allowed_network_hosts": network_authority.allowed_network_hosts,
            "maven_provider_hosts": ("repo.maven.apache.org",),
            "scm_provider_hosts": ("codeload.github.com", "github.com"),
            "maven_provider_source_hash": bytes_hash(maven_provider_source),
            "scm_provider_source_hash": bytes_hash(scm_provider_source),
        }
        result = cls(**body, configuration_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        data = _strict(value, cls, "provider configuration")
        result = cls(
            **{
                **data,
                "allowed_network_hosts": tuple(data["allowed_network_hosts"]),
                "maven_provider_hosts": tuple(data["maven_provider_hosts"]),
                "scm_provider_hosts": tuple(data["scm_provider_hosts"]),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10AcquisitionLedgerContextTemplate:
    schema_version: int
    contract_role: str
    execution_scope: str
    acquisition_run_id: str
    candidate_pool_hash: str
    official_candidate_pool_binding_hash: str
    official_acquisition_policy_hash: str
    final_authorization_hash: str
    route_identity_bundle_hash: str
    exact_freeze_sha_source: str
    template_hash: str

    ROLE: ClassVar[str] = "M336K10_ACQUISITION_LEDGER_CONTEXT_TEMPLATE"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("template_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "template_hash": self.template_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or self.acquisition_run_id not in M336K_OFFICIAL_ACQUISITION_RUN_IDS
            or self.exact_freeze_sha_source != "FINAL_COMMITTED_FREEZE_SHA"
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.template_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 acquisition ledger template is invalid")

    @classmethod
    def build(cls, **values: str) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
            "exact_freeze_sha_source": "FINAL_COMMITTED_FREEZE_SHA",
            **values,
        }
        result = cls(**body, template_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "acquisition ledger template"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10StageRequestAcquisitionBinding:
    schema_version: int
    contract_role: str
    execution_scope: str
    official_candidate_pool_binding_hash: str
    network_authority_manifest_hash: str
    official_acquisition_policy_hash: str
    final_authorization_hash: str
    provider_configuration_hash: str
    acquisition_ledger_context_template_hash: str
    binding_hash: str

    ROLE: ClassVar[str] = "M336K10_STAGE_REQUEST_ACQUISITION_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_hash": self.binding_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 stage-request binding is invalid")

    @classmethod
    def build(cls, **hashes: str) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
            **hashes,
        }
        result = cls(**body, binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "stage-request binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10OfficialAcquisitionBindingReceipt:
    schema_version: int
    contract_role: str
    execution_scope: str
    candidate_pool_binding_hash: str
    candidate_pool_semantic_hash: str
    candidate_pool_bytes_hash: str
    network_authority_manifest_hash: str
    host_set_hash: str
    official_acquisition_policy_hash: str
    final_authorization_hash: str
    active_profile_hash: str
    provider_configuration_hash: str
    stage_request_acquisition_binding_hash: str
    acquisition_ledger_context_template_hash: str
    authorization_binding_hash: str
    pool_policy_authorization_provider_mismatch_count: int
    fixture_host_occurrence_count: int
    unknown_host_count: int
    non_https_endpoint_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K10_OFFICIAL_ACQUISITION_BINDING_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != M336K10_EXECUTION_SCOPE_OFFICIAL
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.pool_policy_authorization_provider_mismatch_count != 0
            or self.fixture_host_occurrence_count != 0
            or self.unknown_host_count != 0
            or self.non_https_endpoint_count != 0
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 official acquisition receipt is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "official acquisition receipt"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10FreezeOriginEntry:
    component_name: str
    execution_scope: str
    producer_role: str
    source_artifact_hash: str
    consumer_roles: tuple[str, ...]
    status: str

    def verify(self) -> None:
        if (
            not self.component_name
            or self.execution_scope not in M336K10_EXECUTION_SCOPES
            or not self.producer_role
            or not _is_hash(self.source_artifact_hash)
            or not self.consumer_roles
            or self.status != "PASS"
        ):
            raise M336K2ProtocolError("M336K10 freeze origin entry is invalid")


@dataclass(frozen=True)
class M336K10FreezeOriginReceipt:
    schema_version: int
    contract_role: str
    entries: tuple[M336K10FreezeOriginEntry, ...]
    component_count: int
    rehearsal_scope_component_count: int
    fixture_host_occurrence_count: int
    wrong_pool_occurrence_count: int
    unclassified_component_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K10_OFFICIAL_FREEZE_ORIGIN_RECEIPT"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "entries": tuple(asdict(item) for item in self.entries),
            "component_count": self.component_count,
            "rehearsal_scope_component_count": self.rehearsal_scope_component_count,
            "fixture_host_occurrence_count": self.fixture_host_occurrence_count,
            "wrong_pool_occurrence_count": self.wrong_pool_occurrence_count,
            "unclassified_component_count": self.unclassified_component_count,
            "status": self.status,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        for entry in self.entries:
            entry.verify()
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.component_count != len(self.entries)
            or tuple(item.component_name for item in self.entries)
            != tuple(sorted(item.component_name for item in self.entries))
            or self.rehearsal_scope_component_count != 0
            or self.fixture_host_occurrence_count != 0
            or self.wrong_pool_occurrence_count != 0
            or self.unclassified_component_count != 0
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 freeze origin receipt is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        data = _strict(value, cls, "freeze origin receipt")
        result = cls(
            **{
                **data,
                "entries": tuple(
                    M336K10FreezeOriginEntry(
                        **{**item, "consumer_roles": tuple(item["consumer_roles"])}
                    )
                    for item in data["entries"]
                ),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10PreledgerCoverageReceipt:
    schema_version: int
    contract_role: str
    request_source_bytes_hash: str
    controller_source_bytes_hash: str
    binding_source_bytes_hash: str
    worker_source_bytes_hash: str
    validate_only_binding_verification_count: int
    controller_binding_recomputation_count: int
    acquisition_semantic_predicate_count: int
    uncovered_acquisition_predicate_count: int
    route_event_before_acquisition_admission_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K10_PRELEDGER_ACQUISITION_COVERAGE_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = (
            self.request_source_bytes_hash,
            self.controller_source_bytes_hash,
            self.binding_source_bytes_hash,
            self.worker_source_bytes_hash,
            self.receipt_hash,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(not _is_hash(value) for value in hashes)
            or self.validate_only_binding_verification_count != 1
            or self.controller_binding_recomputation_count != 1
            or self.acquisition_semantic_predicate_count
            != len(M336K10_ACQUISITION_SEMANTIC_PREDICATES)
            or self.uncovered_acquisition_predicate_count != 0
            or self.route_event_before_acquisition_admission_count != 0
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 preledger coverage is invalid")


def verify_m336k10_preledger_coverage(
    repository: Path,
) -> M336K10PreledgerCoverageReceipt:
    """Prove acquisition semantics and route-event ordering from frozen sources."""

    root = repository.resolve(strict=True)
    request_bytes = (
        root / "src/ai_brain/stage3/acquisition/m336k8_request.py"
    ).read_bytes()
    controller_bytes = (
        root / "src/ai_brain/stage3/acquisition/m336k5_controller.py"
    ).read_bytes()
    binding_bytes = (
        root / "src/ai_brain/stage3/acquisition/m336k10_binding.py"
    ).read_bytes()
    worker_bytes = (
        root / "src/ai_brain/stage3/acquisition/m336k2_acquisition.py"
    ).read_bytes()
    evidence = _m336k10_preledger_source_evidence(
        request_bytes.decode("utf-8"),
        controller_bytes.decode("utf-8"),
        binding_bytes.decode("utf-8"),
        worker_bytes.decode("utf-8"),
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K10PreledgerCoverageReceipt.ROLE,
        "request_source_bytes_hash": bytes_hash(request_bytes),
        "controller_source_bytes_hash": bytes_hash(controller_bytes),
        "binding_source_bytes_hash": bytes_hash(binding_bytes),
        "worker_source_bytes_hash": bytes_hash(worker_bytes),
        **evidence,
        "status": "PASS",
    }
    result = M336K10PreledgerCoverageReceipt(**body, receipt_hash=content_hash(body))
    result.verify()
    return result


def _m336k10_preledger_source_evidence(
    request_source: str,
    controller_source: str,
    binding_source: str,
    worker_source: str,
) -> dict[str, int]:
    validate_marker = "acquisition_binding = _verify_m336k10_acquisition_components("
    admission_marker = "controller_admission = verify_m336k_controller_admission("
    recompute_marker = (
        "recomputed_acquisition_binding = recompute_m336k10_acquisition_binding("
    )
    route_event_marker = "ledger.append("
    validate_count = request_source.count(validate_marker)
    recompute_count = controller_source.count(recompute_marker)
    try:
        semantic_binding_source = binding_source[
            binding_source.index(
                "class M336K10OfficialAcquisitionPolicy"
            ) : binding_source.index("def _derive_endpoint_rows")
        ]
    except ValueError as error:
        raise M336K2ProtocolError(
            "M336K10 semantic binding verifier is absent"
        ) from error
    uncovered = tuple(
        predicate
        for predicate in M336K10_ACQUISITION_SEMANTIC_PREDICATES
        if predicate in worker_source and predicate not in semantic_binding_source
    )
    try:
        validate_before_admission = request_source.index(
            validate_marker
        ) < request_source.index(admission_marker)
        recompute_before_event = controller_source.index(
            recompute_marker
        ) < controller_source.index(route_event_marker)
    except ValueError as error:
        raise M336K2ProtocolError(
            "M336K10 preledger acquisition admission is absent"
        ) from error
    route_event_before = int(
        not validate_before_admission or not recompute_before_event
    )
    if validate_count != 1 or recompute_count != 1 or uncovered or route_event_before:
        raise M336K2ProtocolError("M336K10 preledger acquisition admission changed")
    return {
        "validate_only_binding_verification_count": validate_count,
        "controller_binding_recomputation_count": recompute_count,
        "acquisition_semantic_predicate_count": len(
            M336K10_ACQUISITION_SEMANTIC_PREDICATES
        ),
        "uncovered_acquisition_predicate_count": len(uncovered),
        "route_event_before_acquisition_admission_count": route_event_before,
    }


def build_m336k10_official_pool_binding(
    pool: dict[str, Any], pool_bytes: bytes
) -> tuple[M336K10OfficialCandidatePoolBinding, M336K10NetworkAuthorityManifest]:
    # Keep the legacy candidate validator behind the builder boundary.  The
    # acquisition worker imports authorization/profile contracts, so importing
    # it at module load time would make the v3 authorization graph cyclic.
    from ai_brain.stage3.acquisition.m336k2_acquisition import (
        validate_m336k2_candidate_pool,
    )

    candidates = validate_m336k2_candidate_pool(pool)
    canonical_bytes = canonical_json(pool).encode("utf-8") + b"\n"
    if pool_bytes != canonical_bytes:
        raise M336K2ProtocolError("M336K10 candidate-pool bytes are not canonical")
    identity_rows = tuple(
        {
            "ordinal": ordinal,
            "family_id": item["family_id"],
            "organization_id": item["organization_id"],
            "coordinate": item["coordinate"],
            "source_url": item["source_url"],
            "pom_url": item["pom_url"],
            "scm_repository": item["scm_repository"],
            "scm_commit": item["scm_commit"],
            "candidate_policy_hash": item["policy_hash"],
        }
        for ordinal, item in enumerate(candidates, 1)
    )
    url_rows = tuple(
        (
            ordinal,
            item["family_id"],
            item["source_url"],
            item["pom_url"],
            item["scm_repository"],
            item.get("scm_archive_head_url"),
        )
        for ordinal, item in enumerate(candidates, 1)
    )
    endpoints = _derive_endpoint_rows(candidates)
    hosts = tuple(sorted({item.hostname for item in endpoints}))
    authority_hash = content_hash(
        (
            hosts,
            tuple(
                (
                    item.candidate_ordinal,
                    item.family_id,
                    item.purpose,
                    item.normalized_url,
                )
                for item in endpoints
            ),
        )
    )
    binding_body = {
        "schema_version": 1,
        "contract_role": M336K10OfficialCandidatePoolBinding.ROLE,
        "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
        "pool_semantic_hash": pool["pool_hash"],
        "pool_bytes_hash": bytes_hash(pool_bytes),
        "candidate_count": len(candidates),
        "organization_count": len({item["organization_id"] for item in candidates}),
        "maximum_candidates_per_organization": max(
            Counter(item["organization_id"] for item in candidates).values()
        ),
        "ordered_candidate_identity_manifest_hash": content_hash(identity_rows),
        "ordered_family_id_manifest_hash": content_hash(
            tuple(item["family_id"] for item in candidates)
        ),
        "candidate_url_manifest_hash": content_hash(url_rows),
        "derived_network_authority_hash": authority_hash,
    }
    binding = M336K10OfficialCandidatePoolBinding(
        **binding_body, binding_hash=content_hash(binding_body)
    )
    binding.verify()
    manifest_body = {
        "schema_version": 1,
        "contract_role": M336K10NetworkAuthorityManifest.ROLE,
        "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
        "endpoints": tuple(item.canonical_object() for item in endpoints),
        "allowed_network_hosts": hosts,
        "host_set_hash": content_hash(hosts),
        "url_manifest_hash": content_hash(
            tuple(item.endpoint_hash for item in endpoints)
        ),
        "derived_network_authority_hash": authority_hash,
        "pool_binding_hash": binding.binding_hash,
        "unknown_host_count": len(set(hosts) - set(M336K10_REQUIRED_OFFICIAL_HOSTS)),
        "non_https_endpoint_count": 0,
        "host_normalization_collision_count": 0,
        "fixture_host_occurrence_count": sum(
            host == "fixture.invalid" for host in hosts
        ),
    }
    manifest = M336K10NetworkAuthorityManifest(
        schema_version=manifest_body["schema_version"],
        contract_role=manifest_body["contract_role"],
        execution_scope=manifest_body["execution_scope"],
        endpoints=endpoints,
        allowed_network_hosts=hosts,
        host_set_hash=manifest_body["host_set_hash"],
        url_manifest_hash=manifest_body["url_manifest_hash"],
        derived_network_authority_hash=authority_hash,
        pool_binding_hash=binding.binding_hash,
        unknown_host_count=manifest_body["unknown_host_count"],
        non_https_endpoint_count=0,
        host_normalization_collision_count=0,
        fixture_host_occurrence_count=manifest_body["fixture_host_occurrence_count"],
        manifest_hash=content_hash(manifest_body),
    )
    manifest.verify()
    return binding, manifest


def build_official_acquisition_components(
    *,
    pool: dict[str, Any],
    pool_bytes: bytes,
    profile: M336KOfficialRouteProfile,
    archive_policy_hash: str,
    candidate_terminal_policy_hash: str,
    global_continuation_policy_hash: str,
    authority_statement_hash: str,
    disclosure_registry_manifest_hash: str,
    selector_policy: dict[str, Any],
    selector_policy_hash: str,
    maven_provider_source: bytes,
    scm_provider_source: bytes,
) -> dict[str, Any]:
    """Build official acquisition components solely from official/shared inputs."""

    binding, network = build_m336k10_official_pool_binding(pool, pool_bytes)
    shared = M336K10SharedPolicyBinding.build(
        archive_policy_hash=archive_policy_hash,
        candidate_terminal_policy_hash=candidate_terminal_policy_hash,
        global_continuation_policy_hash=global_continuation_policy_hash,
        authority_statement_hash=authority_statement_hash,
        disclosure_registry_manifest_hash=disclosure_registry_manifest_hash,
        selector_policy_hash=selector_policy_hash,
    )
    policy = M336K10OfficialAcquisitionPolicy.build(
        pool_binding=binding,
        network_authority=network,
        profile=profile,
        shared_policy=shared,
        selector_policy=selector_policy,
    )
    provider = M336K10ProviderConfiguration.build(
        pool_binding=binding,
        network_authority=network,
        maven_provider_source=maven_provider_source,
        scm_provider_source=scm_provider_source,
    )
    authorization_binding_hash = content_hash(
        (
            binding.binding_hash,
            network.manifest_hash,
            policy.acquisition_policy_hash,
            profile.profile_hash,
            provider.configuration_hash,
        )
    )
    return {
        "pool_binding": binding,
        "network_authority": network,
        "shared_policy": shared,
        "acquisition_policy": policy,
        "provider_configuration": provider,
        "authorization_binding_hash": authorization_binding_hash,
    }


def build_rehearsal_acquisition_components(
    *, acquisition_policy: dict[str, Any], acquisition_run_id: str
) -> dict[str, Any]:
    """Retarget a rehearsal policy only within the rehearsal execution scope."""

    body = dict(acquisition_policy)
    body.pop("acquisition_policy_hash", None)
    body.update(
        {
            "contract_role": "M336K5_CANDIDATE_ISOLATED_ACQUISITION_POLICY",
            "policy_version": "m336k5.candidate-isolated-final.v1",
            "acquisition_run_id": acquisition_run_id,
        }
    )
    return {**body, "acquisition_policy_hash": content_hash(body)}


def build_m336k10_post_authorization_components(
    *,
    pool_binding: M336K10OfficialCandidatePoolBinding,
    network_authority: M336K10NetworkAuthorityManifest,
    policy: M336K10OfficialAcquisitionPolicy,
    profile: M336KOfficialRouteProfile,
    provider: M336K10ProviderConfiguration,
    authorization: Any,
    route_identity_bundle_hash: str,
    authorization_binding_hash: str,
) -> dict[str, Any]:
    ledger = M336K10AcquisitionLedgerContextTemplate.build(
        acquisition_run_id=profile.acquisition_run_id,
        candidate_pool_hash=pool_binding.pool_semantic_hash,
        official_candidate_pool_binding_hash=pool_binding.binding_hash,
        official_acquisition_policy_hash=policy.acquisition_policy_hash,
        final_authorization_hash=authorization.authorization_hash,
        route_identity_bundle_hash=route_identity_bundle_hash,
    )
    stage = M336K10StageRequestAcquisitionBinding.build(
        official_candidate_pool_binding_hash=pool_binding.binding_hash,
        network_authority_manifest_hash=network_authority.manifest_hash,
        official_acquisition_policy_hash=policy.acquisition_policy_hash,
        final_authorization_hash=authorization.authorization_hash,
        provider_configuration_hash=provider.configuration_hash,
        acquisition_ledger_context_template_hash=ledger.template_hash,
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K10OfficialAcquisitionBindingReceipt.ROLE,
        "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
        "candidate_pool_binding_hash": pool_binding.binding_hash,
        "candidate_pool_semantic_hash": pool_binding.pool_semantic_hash,
        "candidate_pool_bytes_hash": pool_binding.pool_bytes_hash,
        "network_authority_manifest_hash": network_authority.manifest_hash,
        "host_set_hash": network_authority.host_set_hash,
        "official_acquisition_policy_hash": policy.acquisition_policy_hash,
        "final_authorization_hash": authorization.authorization_hash,
        "active_profile_hash": profile.profile_hash,
        "provider_configuration_hash": provider.configuration_hash,
        "stage_request_acquisition_binding_hash": stage.binding_hash,
        "acquisition_ledger_context_template_hash": ledger.template_hash,
        "authorization_binding_hash": authorization_binding_hash,
        "pool_policy_authorization_provider_mismatch_count": 0,
        "fixture_host_occurrence_count": 0,
        "unknown_host_count": network_authority.unknown_host_count,
        "non_https_endpoint_count": network_authority.non_https_endpoint_count,
        "status": "PASS",
    }
    receipt = M336K10OfficialAcquisitionBindingReceipt(
        **body, receipt_hash=content_hash(body)
    )
    receipt.verify()
    return {"ledger_context": ledger, "stage_binding": stage, "receipt": receipt}


def verify_m336k10_official_acquisition_binding(
    *,
    pool: dict[str, Any],
    pool_bytes: bytes,
    pool_binding: M336K10OfficialCandidatePoolBinding,
    network_authority: M336K10NetworkAuthorityManifest,
    policy: M336K10OfficialAcquisitionPolicy,
    profile: M336KOfficialRouteProfile,
    shared_policy: M336K10SharedPolicyBinding,
    provider: M336K10ProviderConfiguration,
    authorization: Any,
    ledger_context: M336K10AcquisitionLedgerContextTemplate,
    stage_binding: M336K10StageRequestAcquisitionBinding,
    authority_statement_bytes: bytes,
    disclosure_registry_manifest_bytes: bytes,
    maven_provider_source: bytes,
    scm_provider_source: bytes,
    expected_receipt: M336K10OfficialAcquisitionBindingReceipt | None = None,
) -> M336K10OfficialAcquisitionBindingReceipt:
    """Recompute every official acquisition predicate without writing state."""

    actual_binding, actual_network = build_m336k10_official_pool_binding(
        pool, pool_bytes
    )
    policy.verify()
    profile.verify()
    shared_policy.verify()
    provider.verify()
    ledger_context.verify()
    stage_binding.verify()
    authorization.verify()
    rebuilt_provider = M336K10ProviderConfiguration.build(
        pool_binding=actual_binding,
        network_authority=actual_network,
        maven_provider_source=maven_provider_source,
        scm_provider_source=scm_provider_source,
    )
    expected_authorization_binding = content_hash(
        (
            actual_binding.binding_hash,
            actual_network.manifest_hash,
            policy.acquisition_policy_hash,
            profile.profile_hash,
            rebuilt_provider.configuration_hash,
        )
    )
    mismatches = (
        int(pool_binding != actual_binding)
        + int(network_authority != actual_network)
        + int(policy.candidate_pool_hash != actual_binding.pool_semantic_hash)
        + int(
            policy.official_candidate_pool_binding_hash != actual_binding.binding_hash
        )
        + int(policy.network_authority_manifest_hash != actual_network.manifest_hash)
        + int(policy.derived_host_set_hash != actual_network.host_set_hash)
        + int(policy.allowed_network_hosts != actual_network.allowed_network_hosts)
        + int(policy.acquisition_run_id != profile.acquisition_run_id)
        + int(shared_policy.binding_hash != policy.shared_policy_binding_hash)
        + int(shared_policy.archive_policy_hash != policy.archive_policy_hash)
        + int(
            shared_policy.candidate_terminal_policy_hash
            != policy.candidate_terminal_policy_hash
        )
        + int(
            shared_policy.global_continuation_policy_hash
            != policy.global_continuation_policy_hash
        )
        + int(bytes_hash(authority_statement_bytes) != policy.authority_statement_hash)
        + int(
            bytes_hash(disclosure_registry_manifest_bytes)
            != policy.disclosure_registry_manifest_hash
        )
        + int(provider != rebuilt_provider)
        + int(
            getattr(authorization, "candidate_pool_hash", None)
            != actual_binding.pool_semantic_hash
        )
        + int(
            getattr(authorization, "pool_bytes_hash", None)
            != actual_binding.pool_bytes_hash
        )
        + int(
            getattr(authorization, "official_candidate_pool_binding_hash", None)
            != actual_binding.binding_hash
        )
        + int(
            getattr(authorization, "network_authority_manifest_hash", None)
            != actual_network.manifest_hash
        )
        + int(
            getattr(authorization, "derived_host_set_hash", None)
            != actual_network.host_set_hash
        )
        + int(
            getattr(authorization, "allowed_network_hosts", None)
            != actual_network.allowed_network_hosts
        )
        + int(
            getattr(authorization, "official_acquisition_policy_hash", None)
            != policy.acquisition_policy_hash
        )
        + int(
            getattr(authorization, "acquisition_policy_hash", None)
            != policy.acquisition_policy_hash
        )
        + int(
            getattr(authorization, "acquisition_binding_receipt_hash", None)
            != expected_authorization_binding
        )
        + int(
            ledger_context.final_authorization_hash != authorization.authorization_hash
        )
        + int(ledger_context.candidate_pool_hash != actual_binding.pool_semantic_hash)
        + int(
            stage_binding.final_authorization_hash != authorization.authorization_hash
        )
        + int(stage_binding.provider_configuration_hash != provider.configuration_hash)
        + int(
            stage_binding.acquisition_ledger_context_template_hash
            != ledger_context.template_hash
        )
    )
    if mismatches:
        raise M336K2ProtocolError("M336K10 official acquisition binding rejected")
    built = build_m336k10_post_authorization_components(
        pool_binding=actual_binding,
        network_authority=actual_network,
        policy=policy,
        profile=profile,
        provider=provider,
        authorization=authorization,
        route_identity_bundle_hash=ledger_context.route_identity_bundle_hash,
        authorization_binding_hash=expected_authorization_binding,
    )["receipt"]
    if (
        built.stage_request_acquisition_binding_hash != stage_binding.binding_hash
        or built.acquisition_ledger_context_template_hash
        != ledger_context.template_hash
        or expected_receipt is not None
        and built != expected_receipt
    ):
        raise M336K2ProtocolError("M336K10 official acquisition receipt changed")
    return built


def _derive_endpoint_rows(
    candidates: tuple[dict[str, Any], ...],
) -> tuple[M336K10NetworkEndpointBinding, ...]:
    result: list[M336K10NetworkEndpointBinding] = []
    for ordinal, candidate in enumerate(candidates, 1):
        source = candidate["source_url"]
        pom = candidate["pom_url"]
        repository = candidate["scm_repository"]
        parsed_repository = urllib.parse.urlsplit(repository)
        repository_path = parsed_repository.path.removesuffix(".git").strip("/")
        archive_request = (
            f"https://github.com/{repository_path}/archive/"
            f"{candidate['scm_commit']}.zip"
        )
        urls = (
            ("SOURCE_JAR", source),
            ("SOURCE_SHA256_SIDECAR", f"{source}.sha256"),
            ("SOURCE_SIGNATURE", f"{source}.asc"),
            ("POM", pom),
            ("POM_SHA256_SIDECAR", f"{pom}.sha256"),
            ("POM_SIGNATURE", f"{pom}.asc"),
            ("SCM_REF", repository),
            ("SCM_ARCHIVE_REQUEST", archive_request),
            ("SCM_ARCHIVE_FINAL", candidate["scm_archive_head_url"]),
        )
        for purpose, url in urls:
            result.append(
                _endpoint(
                    ordinal=ordinal,
                    family_id=candidate["family_id"],
                    organization_id=candidate["organization_id"],
                    purpose=purpose,
                    raw_url=url,
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.candidate_ordinal,
                item.purpose.encode("utf-8"),
                item.normalized_url.encode("utf-8"),
            ),
        )
    )


def _endpoint(
    *,
    ordinal: int,
    family_id: str,
    organization_id: str,
    purpose: str,
    raw_url: str,
) -> M336K10NetworkEndpointBinding:
    if type(raw_url) is not str:
        raise M336K2ProtocolError("M336K10 official candidate URL is not text")
    parsed = urllib.parse.urlsplit(raw_url)
    hostname = parsed.hostname
    raw_host = parsed.netloc.rsplit("@", 1)[-1]
    if raw_host.startswith("["):
        raw_host = raw_host.split("]", 1)[0] + "]"
    elif ":" in raw_host:
        raw_host = raw_host.rsplit(":", 1)[0]
    try:
        ipaddress.ip_address(hostname or "")
    except ValueError:
        ip_literal = False
    else:
        ip_literal = True
    if (
        parsed.scheme != "https"
        or hostname is None
        or raw_host != hostname
        or hostname != hostname.lower()
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.fragment
        or ip_literal
        or hostname not in M336K10_REQUIRED_OFFICIAL_HOSTS
    ):
        raise M336K2ProtocolError("M336K10 official candidate URL is not canonical")
    normalized = urllib.parse.urlunsplit(
        ("https", hostname, parsed.path, parsed.query, "")
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K10NetworkEndpointBinding.ROLE,
        "execution_scope": M336K10_EXECUTION_SCOPE_OFFICIAL,
        "candidate_ordinal": ordinal,
        "family_id": family_id,
        "organization_id": organization_id,
        "purpose": purpose,
        "normalized_url": normalized,
        "normalized_url_hash": content_hash(normalized),
        "scheme": "https",
        "hostname": hostname,
        "port": 443,
    }
    result = M336K10NetworkEndpointBinding(**body, endpoint_hash=content_hash(body))
    result.verify()
    return result


def read_provider_sources(repository: Path) -> tuple[bytes, bytes]:
    root = repository.resolve(strict=True)
    return (
        (root / "src/ai_brain/stage3/acquisition/maven_provenance.py").read_bytes(),
        (root / "src/ai_brain/stage3/acquisition/scm_revision.py").read_bytes(),
    )
