"""F13-frozen deterministic selector for untouched Java 21 source snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import tree_sitter_java
from tree_sitter import Language, Parser

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    load_m335_disclosed_corpus_denylist,
)
from ai_brain.stage3.acquisition.java_release import JAVA_TARGET_RELEASE

JAVA_SOURCE_SELECTOR_VERSION = "m344.final-java-selector.v1"
M344_PRIOR_CORPUS_DENYLIST_MANIFEST_HASH = (
    "3b1dd97f81fffc6c6aee25267d49729e44b56d62fd217f208cfaf2a25d91d385"
)
_ELIGIBLE_TYPE_NODES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)
_CALLABLE_NODES = frozenset(
    {
        "method_declaration",
        "annotation_type_element_declaration",
        "constructor_declaration",
        "compact_constructor_declaration",
    }
)


@dataclass(frozen=True)
class JavaSourceFamily:
    family_id: str
    version: str
    source_archive_url: str
    license_spdx: str


@dataclass(frozen=True)
class JavaFinalSourceSelectorPolicy:
    target_release: int
    families: tuple[JavaSourceFamily, ...]
    eligible_suffixes: tuple[str, ...]
    excluded_parts: tuple[str, ...]
    minimums: tuple[tuple[str, int], ...]
    maximum_files: int
    maximum_total_bytes: int
    selection_strategy: str
    prior_corpus_hash_denylist: tuple[str, ...]
    required_licenses: tuple[str, ...]
    policy_hash: str


def frozen_final_source_selector_policy(
    *, prior_corpus_hash_denylist: tuple[str, ...] = ()
) -> JavaFinalSourceSelectorPolicy:
    families = (
        JavaSourceFamily(
            "apache-commons-lang3",
            "3.17.0",
            "https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0-sources.jar",
            "Apache-2.0",
        ),
        JavaSourceFamily(
            "apache-commons-collections4",
            "4.5.0",
            "https://repo.maven.apache.org/maven2/org/apache/commons/commons-collections4/4.5.0/commons-collections4-4.5.0-sources.jar",
            "Apache-2.0",
        ),
        JavaSourceFamily(
            "apache-commons-io",
            "2.18.0",
            "https://repo.maven.apache.org/maven2/commons-io/commons-io/2.18.0/commons-io-2.18.0-sources.jar",
            "Apache-2.0",
        ),
    )
    disclosed = load_m335_disclosed_corpus_denylist()
    permanent_denylist = (
        *disclosed["raw_source_hashes"],
        *disclosed["canonical_text_hashes"],
    )
    body = {
        "target_release": JAVA_TARGET_RELEASE,
        "families": families,
        "eligible_suffixes": (".java",),
        "excluded_parts": (
            "generated",
            "vendor",
            "test",
            "tests",
            "module-info.java",
            "package-info.java",
        ),
        "minimums": (
            ("real_callable_files", 60),
            ("real_callable_targets", 1500),
            ("receiver_types", 150),
            ("packages", 12),
            ("overload_groups", 100),
            ("constructors", 50),
            ("generic_methods", 100),
            ("throws_declarations", 100),
            ("nested_member_targets", 25),
        ),
        "maximum_files": 240,
        "maximum_total_bytes": 16 * 1024 * 1024,
        "selection_strategy": "sha256(F13_SHA + family_id + relative_path), ascending",
        "prior_corpus_hash_denylist": tuple(
            sorted({*prior_corpus_hash_denylist, *permanent_denylist})
        ),
        "required_licenses": ("Apache-2.0",),
    }
    return JavaFinalSourceSelectorPolicy(**body, policy_hash=content_hash(body))


def select_final_java_sources(
    roots: tuple[tuple[str, Path], ...],
    *,
    f13_sha: str,
    policy: JavaFinalSourceSelectorPolicy,
) -> tuple[Path, ...]:
    if len(f13_sha) != 40 or any(char not in "0123456789abcdef" for char in f13_sha):
        raise ValueError("selector requires an exact lowercase F13 SHA")
    allowed = {item.family_id for item in policy.families}
    if len(roots) < 2 or {item[0] for item in roots} - allowed:
        raise ValueError("selector requires at least two allowlisted source roots")
    ranked = []
    total = 0
    for family_id, root in roots:
        resolved = root.resolve(strict=True)
        for path in resolved.rglob("*.java"):
            relative = path.relative_to(resolved).as_posix()
            pure = PurePosixPath(relative)
            lowered = {part.casefold() for part in pure.parts}
            if lowered & set(policy.excluded_parts):
                continue
            raw = path.read_bytes()
            if not _contains_real_callable_type(raw):
                continue
            digest = bytes_hash(raw)
            canonical = (
                raw.decode("utf-8", errors="strict")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .rstrip()
                + "\n"
            )
            canonical_digest = bytes_hash(canonical.encode("utf-8"))
            if (
                digest in policy.prior_corpus_hash_denylist
                or canonical_digest in policy.prior_corpus_hash_denylist
            ):
                continue
            rank = content_hash((f13_sha, family_id, relative))
            ranked.append((rank, family_id, relative, path, len(raw)))
    selected = []
    selected_hashes = set()
    for _rank, _family, _relative, path, size in sorted(ranked):
        if len(selected) >= policy.maximum_files:
            break
        if total + size > policy.maximum_total_bytes:
            continue
        digest = bytes_hash(path.read_bytes())
        if digest in selected_hashes:
            continue
        selected.append(path)
        selected_hashes.add(digest)
        total += size
    if len(selected) < dict(policy.minimums)["real_callable_files"]:
        raise ValueError("eligible final source denominator is below frozen minimum")
    selected_roots = {
        family_id
        for _rank, family_id, _relative, path, _size in ranked
        if path in selected
    }
    if selected_roots != {item[0] for item in roots}:
        raise ValueError("deterministic selection omitted an independent source root")
    return tuple(selected)


def _contains_real_callable_type(raw: bytes) -> bool:
    root = (
        Parser(Language(tree_sitter_java.language()))
        .parse(raw, encoding="utf8")
        .root_node
    )
    has_type = False
    has_callable = False
    pending = [root]
    while pending:
        node = pending.pop()
        has_type = has_type or node.type in _ELIGIBLE_TYPE_NODES
        has_callable = has_callable or node.type in _CALLABLE_NODES
        if has_type and has_callable:
            return True
        pending.extend(node.named_children)
    return False


def selector_receipt(policy, selected, roots, f13_sha):
    root_map = tuple((name, path.resolve(strict=True)) for name, path in roots)
    entries = []
    for path in selected:
        matches = [item for item in root_map if path.resolve().is_relative_to(item[1])]
        if len(matches) != 1:
            raise ValueError("selected source has ambiguous family root")
        family, root = matches[0]
        entries.append(
            (
                family,
                path.resolve().relative_to(root).as_posix(),
                bytes_hash(path.read_bytes()),
            )
        )
    body = {
        "selector_version": JAVA_SOURCE_SELECTOR_VERSION,
        "policy_hash": policy.policy_hash,
        "f13_sha": f13_sha,
        "selected": tuple(entries),
    }
    return {**body, "receipt_hash": content_hash(body)}
