"""Explicit pack identity, exact-reference and search-alias semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash

ALIAS_SEMANTICS_SCHEMA_VERSION = 1
ALIAS_SEMANTICS_DEPENDENCY_PREFIX = "alias-semantics."
ALIAS_SEMANTICS_FILENAME = "alias_semantics.json"


@dataclass(frozen=True)
class AuthoritativeIdentity:
    record_id: str
    authority_kind: str
    canonical_value: str
    identity_hash: str


@dataclass(frozen=True)
class ExactReferenceAlias:
    reference: str
    record_id: str


@dataclass(frozen=True)
class SearchAliasEntry:
    alias: str
    record_ids: tuple[str, ...]


@dataclass(frozen=True)
class AliasSemantics:
    schema_version: int
    authoritative_identities: tuple[AuthoritativeIdentity, ...]
    exact_references: tuple[ExactReferenceAlias, ...]
    search_aliases: tuple[SearchAliasEntry, ...]
    index_hash: str


class AliasLookupStatus(StrEnum):
    EXACT = "EXACT"
    AMBIGUOUS_OVERLOAD = "AMBIGUOUS_OVERLOAD"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class AliasLookupResult:
    query: str
    status: AliasLookupStatus
    record_ids: tuple[str, ...]


def build_alias_semantics(authorities, exact_references, search_aliases):
    authority_values = tuple(sorted(authorities, key=lambda item: item.record_id))
    exact_values = tuple(sorted(exact_references, key=lambda item: item.reference))
    search_values = tuple(
        SearchAliasEntry(alias, tuple(sorted(set(record_ids))))
        for alias, record_ids in sorted(search_aliases.items())
    )
    body = {
        "schema_version": ALIAS_SEMANTICS_SCHEMA_VERSION,
        "authoritative_identities": authority_values,
        "exact_references": exact_values,
        "search_aliases": search_values,
    }
    value = AliasSemantics(**body, index_hash=content_hash(body))
    verify_alias_semantics(value)
    return value


def verify_alias_semantics(value: AliasSemantics, record_ids=None) -> None:
    body = asdict(value)
    claimed = body.pop("index_hash")
    authority_ids = tuple(item.record_id for item in value.authoritative_identities)
    identity_hashes = tuple(
        item.identity_hash for item in value.authoritative_identities
    )
    exact = tuple(item.reference for item in value.exact_references)
    searches = tuple(item.alias for item in value.search_aliases)
    known = set(authority_ids)
    if (
        value.schema_version != ALIAS_SEMANTICS_SCHEMA_VERSION
        or content_hash(body) != claimed
        or authority_ids != tuple(sorted(authority_ids))
        or len(authority_ids) != len(set(authority_ids))
        or len(identity_hashes) != len(set(identity_hashes))
        or exact != tuple(sorted(exact))
        or len(exact) != len(set(exact))
        or searches != tuple(sorted(searches))
        or len(searches) != len(set(searches))
    ):
        raise ValueError("invalid alias semantics index")
    if record_ids is not None and known != set(record_ids):
        raise ValueError("alias authority denominator mismatch")
    if any(item.record_id not in known for item in value.exact_references):
        raise ValueError("exact reference resolves outside authoritative identities")
    if any(
        not item.record_ids
        or item.record_ids != tuple(sorted(set(item.record_ids)))
        or not set(item.record_ids) <= known
        for item in value.search_aliases
    ):
        raise ValueError("search alias index is invalid")


def resolve_alias(value: AliasSemantics, query: str) -> AliasLookupResult:
    exact = {item.reference: item.record_id for item in value.exact_references}
    if query in exact:
        return AliasLookupResult(query, AliasLookupStatus.EXACT, (exact[query],))
    search = {item.alias: item.record_ids for item in value.search_aliases}
    matches = search.get(query.casefold(), ())
    status = (
        AliasLookupStatus.NOT_FOUND
        if not matches
        else (
            AliasLookupStatus.EXACT
            if len(matches) == 1
            else AliasLookupStatus.AMBIGUOUS_OVERLOAD
        )
    )
    return AliasLookupResult(query, status, matches)
