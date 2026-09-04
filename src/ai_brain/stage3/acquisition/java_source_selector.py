"""F13-frozen deterministic selector for untouched Java 21 source snapshots."""

from __future__ import annotations

from collections import Counter
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
M336_JAVA_SOURCE_SELECTOR_VERSION = "m336.final-java-selector.v2"
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
    maximum_root_target_fraction: str
    selection_strategy: str
    prior_corpus_hash_denylist: tuple[str, ...]
    required_licenses: tuple[str, ...]
    policy_hash: str


@dataclass(frozen=True)
class M336FinalCorpusVerification:
    source_tree_hash: str
    selected_relative_path_manifest_hash: str
    real_callable_source_file_count: int
    real_callable_target_count: int
    real_receiver_type_count: int
    real_package_count: int
    real_overload_group_count: int
    real_constructor_count: int
    real_generic_method_count: int
    real_throws_declaration_count: int
    real_nested_member_target_count: int
    named_module_target_count: int
    synthetic_target_count: int
    package_info_callable_file_count: int
    per_root_target_counts: tuple[tuple[str, int], ...]
    maximum_root_target_fraction: str
    raw_source_overlap_count: int
    canonical_source_overlap_count: int
    declaration_fingerprint_overlap_count: int
    normalized_similarity_overlap_count: int
    status: str
    report_hash: str


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
        "maximum_root_target_fraction": "0.800000",
        "selection_strategy": "sha256(F13_SHA + family_id + relative_path), ascending",
        "prior_corpus_hash_denylist": tuple(
            sorted({*prior_corpus_hash_denylist, *permanent_denylist})
        ),
        "required_licenses": ("Apache-2.0",),
    }
    return JavaFinalSourceSelectorPolicy(**body, policy_hash=content_hash(body))


def frozen_m336_final_source_selector_policy(
    *, prior_corpus_hash_denylist: tuple[str, ...] = ()
) -> JavaFinalSourceSelectorPolicy:
    """Finite metadata-only candidate policy frozen before final source acquisition."""

    families = (
        JavaSourceFamily(
            "google-guava",
            "33.4.8-jre",
            "https://repo.maven.apache.org/maven2/com/google/guava/guava/33.4.8-jre/guava-33.4.8-jre-sources.jar",
            "Apache-2.0",
        ),
        JavaSourceFamily(
            "apache-commons-collections4",
            "4.5.0",
            "https://repo.maven.apache.org/maven2/org/apache/commons/commons-collections4/4.5.0/commons-collections4-4.5.0-sources.jar",
            "Apache-2.0",
        ),
        JavaSourceFamily(
            "caffeine",
            "3.2.0",
            "https://repo.maven.apache.org/maven2/com/github/ben-manes/caffeine/caffeine/3.2.0/caffeine-3.2.0-sources.jar",
            "Apache-2.0",
        ),
    )
    disclosed = load_m335_disclosed_corpus_denylist()
    permanent = (
        *disclosed["archive_hashes"],
        *disclosed["raw_source_hashes"],
        *disclosed["canonical_text_hashes"],
        *prior_corpus_hash_denylist,
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
            ("real_callable_files", 100),
            ("real_callable_targets", 2_000),
            ("receiver_types", 175),
            ("packages", 15),
            ("overload_groups", 125),
            ("constructors", 75),
            ("generic_methods", 100),
            ("throws_declarations", 100),
            ("nested_member_targets", 25),
        ),
        "maximum_files": 360,
        "maximum_total_bytes": 24 * 1024 * 1024,
        "maximum_root_target_fraction": "0.800000",
        "selection_strategy": (
            "per-family round-robin of sha256(F15_SHA + family_id + relative_path), "
            "ascending"
        ),
        "prior_corpus_hash_denylist": tuple(sorted(set(permanent))),
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
    by_family = {
        family: [item for item in sorted(ranked) if item[1] == family]
        for family in sorted({item[0] for item in roots})
    }
    while len(selected) < policy.maximum_files and any(by_family.values()):
        progressed = False
        for family in sorted(by_family):
            if not by_family[family] or len(selected) >= policy.maximum_files:
                continue
            _rank, _family, _relative, path, size = by_family[family].pop(0)
            if total + size > policy.maximum_total_bytes:
                continue
            digest = bytes_hash(path.read_bytes())
            if digest in selected_hashes:
                continue
            selected.append(path)
            selected_hashes.add(digest)
            total += size
            progressed = True
        if not progressed:
            break
    if len(selected) < dict(policy.minimums)["real_callable_files"]:
        raise ValueError("eligible final source denominator is below frozen minimum")
    selected_roots = {
        family_id
        for _rank, family_id, _relative, path, _size in ranked
        if path in selected
    }
    if selected_roots != {item[0] for item in roots}:
        raise ValueError("deterministic selection omitted an independent source root")
    target_counts = {
        family: sum(
            _callable_target_count(path.read_bytes())
            for path in selected
            if path.resolve().is_relative_to(
                next(
                    root.resolve(strict=True) for name, root in roots if name == family
                )
            )
        )
        for family in selected_roots
    }
    target_total = sum(target_counts.values())
    if not target_total or any(
        count / target_total > float(policy.maximum_root_target_fraction)
        for count in target_counts.values()
    ):
        raise ValueError("final source root exceeds frozen callable-target share")
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


def _callable_target_count(raw: bytes) -> int:
    root = (
        Parser(Language(tree_sitter_java.language()))
        .parse(raw, encoding="utf8")
        .root_node
    )
    pending = [root]
    count = 0
    while pending:
        node = pending.pop()
        count += node.type in _CALLABLE_NODES
        pending.extend(node.named_children)
    return count


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


def m336_selector_receipt(policy, selected, roots, f15_sha):
    body = selector_receipt(policy, selected, roots, f15_sha)
    body.pop("receipt_hash")
    body["selector_version"] = M336_JAVA_SOURCE_SELECTOR_VERSION
    body["f15_sha"] = body.pop("f13_sha")
    return {**body, "receipt_hash": content_hash(body)}


def verify_m336_final_source_corpus(bundle, source_index, policy):
    """Verify frozen census and all prior-corpus similarity classes after selection."""

    disclosed = load_m335_disclosed_corpus_denylist()
    documents = tuple(bundle.documents)
    callables = tuple(
        item
        for item in source_index.declarations
        if item.member_kind in {"method", "constructor"}
    )
    overloads = Counter((item.receiver_type, item.member_name) for item in callables)
    by_root = Counter(item.source_unit_id.partition("/")[0] for item in callables)
    target_total = len(callables)
    maximum_share = (
        max(by_root.values(), default=0) / target_total if target_total else 1
    )
    fingerprints = {
        content_hash(
            (
                item.receiver_type,
                item.member_kind,
                item.member_name,
                item.canonical_source_signature,
                item.erased_jvm_descriptor,
            )
        )
        for item in callables
    }
    raw_overlap = {item.bytes_hash for item in documents} & set(
        disclosed["raw_source_hashes"]
    )
    canonical_overlap = {item.canonical_text_hash for item in documents} & set(
        disclosed["canonical_text_hashes"]
    )
    declaration_overlap = fingerprints & set(
        disclosed.get("declaration_fingerprints", ())
    )
    rows = tuple(
        (item.relative_path, item.bytes_hash, item.canonical_text_hash)
        for item in documents
    )
    census = {
        "real_callable_files": len({item.source_unit_id for item in callables}),
        "real_callable_targets": target_total,
        "receiver_types": len({item.receiver_type for item in callables}),
        "packages": len({item.package_name for item in callables}),
        "overload_groups": sum(value > 1 for value in overloads.values()),
        "constructors": sum(item.member_kind == "constructor" for item in callables),
        "generic_methods": sum(bool(item.type_parameters) for item in callables),
        "throws_declarations": sum(
            bool(item.declared_exceptions) for item in callables
        ),
        "nested_member_targets": sum(bool(item.nested_type_path) for item in callables),
    }
    failed_minima = tuple(
        key for key, minimum in policy.minimums if census[key] < minimum
    )
    overlaps = len(raw_overlap) + len(canonical_overlap) + len(declaration_overlap)
    status = (
        "PASS"
        if not failed_minima
        and overlaps == 0
        and maximum_share <= float(policy.maximum_root_target_fraction)
        and len(by_root) >= 2
        else "FAIL"
    )
    body = {
        "source_tree_hash": content_hash(rows),
        "selected_relative_path_manifest_hash": content_hash(
            tuple(item.relative_path for item in documents)
        ),
        "real_callable_source_file_count": census["real_callable_files"],
        "real_callable_target_count": target_total,
        "real_receiver_type_count": census["receiver_types"],
        "real_package_count": census["packages"],
        "real_overload_group_count": census["overload_groups"],
        "real_constructor_count": census["constructors"],
        "real_generic_method_count": census["generic_methods"],
        "real_throws_declaration_count": census["throws_declarations"],
        "real_nested_member_target_count": census["nested_member_targets"],
        "named_module_target_count": sum(
            item.module_name is not None for item in callables
        ),
        "synthetic_target_count": 0,
        "package_info_callable_file_count": sum(
            PurePosixPath(item.source_unit_id).name == "package-info.java"
            for item in callables
        ),
        "per_root_target_counts": tuple(sorted(by_root.items())),
        "maximum_root_target_fraction": f"{maximum_share:.6f}",
        "raw_source_overlap_count": len(raw_overlap),
        "canonical_source_overlap_count": len(canonical_overlap),
        "declaration_fingerprint_overlap_count": len(declaration_overlap),
        "normalized_similarity_overlap_count": overlaps,
        "status": status,
    }
    report = M336FinalCorpusVerification(**body, report_hash=content_hash(body))
    if report.status != "PASS":
        raise ValueError(
            "M-33.6 selected corpus fails frozen census, distribution, or denylist"
        )
    return report
