"""Frozen M-33.6d metadata, one-shot acquisition, vault, and selector protocol."""

from __future__ import annotations

import io
import os
import re
import stat
import subprocess
import time
import tracemalloc
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    build_disclosed_java_material_entry,
    load_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.java_source_selector import (
    _contains_real_callable_type,
)
from ai_brain.stage3.acquisition.m336d_authority import (
    M336D_AUTHORITY_STATEMENT_SHA256,
    SourceAuthorizationBinding,
    load_pinned_authority_registry_for_development,
    receipt_public_dict,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY,
    LocalVaultRole,
)
from ai_brain.stage3.acquisition.m336d_correspondence import (
    derive_scm_correspondence_decision,
)
from ai_brain.stage3.acquisition.m336d_legal_inventory import (
    LegalDocumentContainer,
    inventory_legal_documents,
)
from ai_brain.stage3.acquisition.m336d_spdx_expression import parse_spdx_expression
from ai_brain.stage3.acquisition.maven_provenance import (
    MavenCentralProvenanceProvider,
    canonical_source_bytes,
    correspond_source_trees,
    inspect_source_archive,
    maven_coordinate,
    parse_maven_pom,
)
from ai_brain.stage3.acquisition.scm_revision import ScmRevisionProvider
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SourceCorrespondenceStatus,
)
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)

M336D_METADATA_POLICY_VERSION = "m336d.metadata-pool.v1"
M336D_ACQUISITION_RUN_ID = "m336d.fresh-java.global-acquisition.v1"
M336D_SELECTOR_VERSION = "m336d.final-java-selector.v1"
M336D_SELECTOR_SEED = "m336d-fresh-java-freeze-v3-180"
M336D_SELECTED_FILE_COUNT = 180
M336D_MAXIMUM_ROOT_FRACTION = "0.350000"
_COMPLETE = frozenset(
    {
        SourceCorrespondenceStatus.RAW_EXACT_MATCH,
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH,
        SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
    }
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")

M336D_PRIOR_FAMILY_IDS = frozenset(
    {
        "apache-commons-collections4",
        "apache-commons-io",
        "apache-commons-lang3",
        "caffeine",
        "commons-lang3",
        "eclipse-collections",
        "google-guava",
        "gson",
        "guava",
        "httpcore5",
        "jackson",
        "jackson-databind",
        "joda-time",
        "junit-jupiter-api",
        "log4j-api",
        "mockito-core",
        "okio-jvm",
        "openjdk",
        "picocli",
        "reactor-core",
        "slf4j-api",
        "snakeyaml",
    }
)
M336D_PRIOR_COORDINATES = frozenset(
    {
        "com.fasterxml.jackson.core:jackson-databind:2.20.0",
        "com.github.ben-manes.caffeine:caffeine:3.2.0",
        "com.github.ben-manes.caffeine:caffeine:3.2.2",
        "com.google.code.gson:gson:2.13.2",
        "com.google.guava:guava:33.4.8-jre",
        "com.squareup.okio:okio-jvm:3.16.0",
        "commons-io:commons-io:2.18.0",
        "info.picocli:picocli:4.7.7",
        "io.projectreactor:reactor-core:3.7.9",
        "joda-time:joda-time:2.14.0",
        "org.apache.commons:commons-collections4:4.5.0",
        "org.apache.commons:commons-lang3:3.17.0",
        "org.apache.commons:commons-lang3:3.18.0",
        "org.apache.httpcomponents.core5:httpcore5:5.3.6",
        "org.apache.logging.log4j:log4j-api:2.25.2",
        "org.eclipse.collections:eclipse-collections:11.1.0",
        "org.junit.jupiter:junit-jupiter-api:5.13.4",
        "org.mockito:mockito-core:5.19.0",
        "org.slf4j:slf4j-api:2.0.17",
        "org.yaml:snakeyaml:2.4",
    }
)
M336D_PRIOR_SCM_REPOSITORIES = frozenset(
    {
        "https://github.com/FasterXML/jackson-core.git",
        "https://github.com/FasterXML/jackson-databind.git",
        "https://github.com/apache/commons-collections.git",
        "https://github.com/apache/commons-io.git",
        "https://github.com/apache/commons-lang.git",
        "https://github.com/apache/httpcomponents-core.git",
        "https://github.com/apache/logging-log4j2.git",
        "https://github.com/ben-manes/caffeine.git",
        "https://github.com/google/gson.git",
        "https://github.com/google/guava.git",
        "https://github.com/openjdk/jdk.git",
        "https://github.com/qos-ch/slf4j.git",
        "https://github.com/reactor/reactor-core.git",
        "https://github.com/remkop/picocli.git",
        "https://github.com/square/okio.git",
    }
)
M336D_PRIOR_SCM_REFS = frozenset(
    {
        "refs/tags/gson-parent-2.13.2",
        "refs/tags/jackson-databind-2.20.0",
        "refs/tags/rel/2.25.2",
        "refs/tags/rel/commons-collections-4.5.0",
        "refs/tags/rel/commons-io-2.18.0",
        "refs/tags/rel/commons-lang-3.17.0",
        "refs/tags/rel/v5.3.6",
        "refs/tags/v3.2.0",
        "refs/tags/v3.7.9",
        "refs/tags/v33.4.8",
        "refs/tags/v4.7.7",
    }
)


def frozen_prior_identity_denylist() -> dict:
    """Return the complete public identity denylist known before M-33.6d."""

    source_urls = tuple(
        sorted(
            "https://repo.maven.apache.org/maven2/"
            + coordinate.split(":")[0].replace(".", "/")
            + "/"
            + coordinate.split(":")[1]
            + "/"
            + coordinate.split(":")[2]
            + "/"
            + coordinate.split(":")[1]
            + "-"
            + coordinate.split(":")[2]
            + "-sources.jar"
            for coordinate in M336D_PRIOR_COORDINATES
        )
    )
    organization_repositories = tuple(
        sorted(
            "/".join(repository.removesuffix(".git").rsplit("/", 2)[-2:]).lower()
            for repository in M336D_PRIOR_SCM_REPOSITORIES
        )
    )
    return {
        "schema_version": 1,
        "excluded_family_ids": tuple(sorted(M336D_PRIOR_FAMILY_IDS)),
        "excluded_coordinates": tuple(sorted(M336D_PRIOR_COORDINATES)),
        "excluded_source_urls": source_urls,
        "excluded_scm_repositories": tuple(sorted(M336D_PRIOR_SCM_REPOSITORIES)),
        "excluded_scm_refs": tuple(sorted(M336D_PRIOR_SCM_REFS)),
        "excluded_organization_repository_pairs": organization_repositories,
        "disclosed_registry_bound": True,
    }


class _MetadataRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, chain: list[str]):
        self.chain = chain

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != "repo.maven.apache.org":
            raise ValueError("metadata redirect left the frozen Maven host")
        self.chain.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class CandidateSeed:
    family_id: str
    organization_id: str
    group_id: str
    artifact_id: str
    version: str
    scm_repository: str
    scm_ref: str
    repository_source_prefixes: tuple[str, ...] = ()


_SEEDS = (
    CandidateSeed(
        "hikaricp",
        "brettwooldridge",
        "com.zaxxer",
        "HikariCP",
        "6.2.1",
        "https://github.com/brettwooldridge/HikariCP.git",
        "refs/tags/HikariCP-6.2.1",
    ),
    CandidateSeed(
        "jopt-simple",
        "jopt-simple",
        "net.sf.jopt-simple",
        "jopt-simple",
        "6.0-alpha-3",
        "https://github.com/jopt-simple/jopt-simple.git",
        "refs/tags/jopt-simple-6.0-alpha-3",
    ),
    CandidateSeed(
        "classgraph",
        "classgraph",
        "io.github.classgraph",
        "classgraph",
        "4.8.179",
        "https://github.com/classgraph/classgraph.git",
        "refs/tags/classgraph-4.8.179",
    ),
    CandidateSeed(
        "failsafe",
        "jhalterman",
        "dev.failsafe",
        "failsafe",
        "3.3.2",
        "https://github.com/jhalterman/failsafe.git",
        "refs/tags/failsafe-parent-3.3.2",
    ),
    CandidateSeed(
        "checker-qual",
        "typetools",
        "org.checkerframework",
        "checker-qual",
        "3.49.1",
        "https://github.com/typetools/checker-framework.git",
        "refs/tags/checker-framework-3.49.1",
    ),
    CandidateSeed(
        "zstd-jni",
        "luben",
        "com.github.luben",
        "zstd-jni",
        "1.5.7-4",
        "https://github.com/luben/zstd-jni.git",
        "refs/tags/v1.5.7-4",
    ),
    CandidateSeed(
        "lz4-java",
        "lz4",
        "org.lz4",
        "lz4-java",
        "1.8.0",
        "https://github.com/lz4/lz4-java.git",
        "refs/tags/1.8.0",
    ),
    CandidateSeed(
        "hdrhistogram",
        "hdrhistogram",
        "org.hdrhistogram",
        "HdrHistogram",
        "2.2.2",
        "https://github.com/HdrHistogram/HdrHistogram.git",
        "refs/tags/HdrHistogram-2.2.2",
    ),
    CandidateSeed(
        "jctools-core",
        "jctools",
        "org.jctools",
        "jctools-core",
        "4.0.5",
        "https://github.com/JCTools/JCTools.git",
        "refs/tags/v4.0.5",
    ),
    CandidateSeed(
        "jetbrains-annotations",
        "jetbrains",
        "org.jetbrains",
        "annotations",
        "26.0.2",
        "https://github.com/JetBrains/java-annotations.git",
        "refs/tags/26.0.2",
    ),
    CandidateSeed(
        "animal-sniffer",
        "mojohaus",
        "org.codehaus.mojo",
        "animal-sniffer-annotations",
        "1.24",
        "https://github.com/mojohaus/animal-sniffer.git",
        "refs/tags/animal-sniffer-1.24",
    ),
    CandidateSeed(
        "errorprone-annotations",
        "google",
        "com.google.errorprone",
        "error_prone_annotations",
        "2.36.0",
        "https://github.com/google/error-prone.git",
        "refs/tags/v2.36.0",
    ),
    CandidateSeed(
        "reactive-streams",
        "reactive-streams",
        "org.reactivestreams",
        "reactive-streams",
        "1.0.4",
        "https://github.com/reactive-streams/reactive-streams-jvm.git",
        "refs/tags/v1.0.4",
    ),
    CandidateSeed(
        "maven-artifact",
        "apache",
        "org.apache.maven",
        "maven-artifact",
        "3.9.9",
        "https://github.com/apache/maven.git",
        "refs/tags/maven-3.9.9",
    ),
    CandidateSeed(
        "objenesis",
        "easymock",
        "org.objenesis",
        "objenesis",
        "3.4",
        "https://github.com/easymock/objenesis.git",
        "refs/tags/3.4",
    ),
    CandidateSeed(
        "byte-buddy",
        "raphw",
        "net.bytebuddy",
        "byte-buddy",
        "1.15.11",
        "https://github.com/raphw/byte-buddy.git",
        "refs/tags/byte-buddy-1.15.11",
    ),
    CandidateSeed(
        "awaitility",
        "awaitility",
        "org.awaitility",
        "awaitility",
        "4.3.0",
        "https://github.com/awaitility/awaitility.git",
        "refs/tags/awaitility-4.3.0",
    ),
    CandidateSeed(
        "java-semver",
        "zafarkhaja",
        "com.github.zafarkhaja",
        "java-semver",
        "0.10.2",
        "https://github.com/zafarkhaja/jsemver.git",
        "refs/tags/v0.10.2",
    ),
    CandidateSeed(
        "vavr",
        "vavr",
        "io.vavr",
        "vavr",
        "0.10.6",
        "https://github.com/vavr-io/vavr.git",
        "refs/tags/v0.10.6",
    ),
    CandidateSeed(
        "pcollections",
        "hrldcpr",
        "org.pcollections",
        "pcollections",
        "4.0.2",
        "https://github.com/hrldcpr/pcollections.git",
        "refs/tags/v4.0.2",
    ),
    CandidateSeed(
        "agrona",
        "real-logic",
        "org.agrona",
        "agrona",
        "1.23.1",
        "https://github.com/real-logic/agrona.git",
        "refs/tags/1.23.1",
    ),
    CandidateSeed(
        "disruptor",
        "lmax",
        "com.lmax",
        "disruptor",
        "4.0.0",
        "https://github.com/LMAX-Exchange/disruptor.git",
        "refs/tags/4.0.0",
    ),
    CandidateSeed(
        "mapstruct",
        "mapstruct",
        "org.mapstruct",
        "mapstruct",
        "1.6.3",
        "https://github.com/mapstruct/mapstruct.git",
        "refs/tags/1.6.3",
    ),
    CandidateSeed(
        "modelmapper",
        "modelmapper",
        "org.modelmapper",
        "modelmapper",
        "3.2.2",
        "https://github.com/modelmapper/modelmapper.git",
        "refs/tags/modelmapper-parent-3.2.2",
    ),
    CandidateSeed(
        "roaringbitmap",
        "roaringbitmap",
        "org.roaringbitmap",
        "RoaringBitmap",
        "1.3.0",
        "https://github.com/RoaringBitmap/RoaringBitmap.git",
        "refs/tags/1.3.0",
    ),
    CandidateSeed(
        "fastutil",
        "vigna",
        "it.unimi.dsi",
        "fastutil",
        "8.5.15",
        "https://github.com/vigna/fastutil.git",
        "refs/tags/8.5.15",
    ),
    CandidateSeed(
        "moshi",
        "square",
        "com.squareup.moshi",
        "moshi",
        "1.15.2",
        "https://github.com/square/moshi.git",
        "refs/tags/1.15.2",
    ),
    CandidateSeed(
        "jna",
        "java-native-access",
        "net.java.dev.jna",
        "jna",
        "5.16.0",
        "https://github.com/java-native-access/jna.git",
        "refs/tags/5.16.0",
    ),
    CandidateSeed(
        "dagger",
        "google",
        "com.google.dagger",
        "dagger",
        "2.55",
        "https://github.com/google/dagger.git",
        "refs/tags/dagger-2.55",
    ),
    CandidateSeed(
        "jakarta-inject",
        "eclipse-ee4j",
        "jakarta.inject",
        "jakarta.inject-api",
        "2.0.1",
        "https://github.com/eclipse-ee4j/injection-api.git",
        "refs/tags/2.0.1",
    ),
)


def frozen_candidate_seeds() -> tuple[CandidateSeed, ...]:
    """Return metadata identities only; no source-body facts are embedded here."""

    organizations = Counter(item.organization_id for item in _SEEDS)
    if len(_SEEDS) < 24 or len(organizations) < 16 or max(organizations.values()) > 2:
        raise AssertionError("candidate seed diversity contract failed")
    denylist = frozen_prior_identity_denylist()
    candidate_coordinates = {
        f"{item.group_id}:{item.artifact_id}:{item.version}" for item in _SEEDS
    }
    candidate_pairs = {
        "/".join(item.scm_repository.removesuffix(".git").rsplit("/", 2)[-2:]).lower()
        for item in _SEEDS
    }
    if (
        {item.family_id for item in _SEEDS} & set(denylist["excluded_family_ids"])
        or candidate_coordinates & set(denylist["excluded_coordinates"])
        or {item.scm_repository for item in _SEEDS}
        & set(denylist["excluded_scm_repositories"])
        or {item.scm_ref for item in _SEEDS} & set(denylist["excluded_scm_refs"])
        or candidate_pairs & set(denylist["excluded_organization_repository_pairs"])
    ):
        raise AssertionError("candidate seed overlaps a prior M-33 identity")
    return _SEEDS


def scan_local_cache_names(
    roots: tuple[tuple[str, Path], ...], *, platform: str
) -> dict:
    """Inspect names and metadata only; never open a candidate source body."""

    seeds = frozen_candidate_seeds()
    source_names = {
        f"{item.artifact_id}-{item.version}-sources.jar".casefold(): item
        for item in seeds
    }
    repository_names = {
        item: item.scm_repository.removesuffix(".git").rsplit("/", 1)[-1].casefold()
        for item in seeds
    }
    rows_by_key = {}

    def record(seed: CandidateSeed, cache_class: str, reason: str) -> None:
        row_body = {
            "discovered_candidate_identity": seed.family_id,
            "family_id": seed.family_id,
            "cache_class": cache_class,
            "excluded": True,
            "reason": reason,
        }
        key = (seed.family_id, cache_class, reason)
        rows_by_key[key] = {**row_body, "receipt_hash": content_hash(row_body)}

    for cache_class, root in roots:
        if not root.exists():
            continue
        for directory, children, files in os.walk(root):
            directory_name = Path(directory).name.casefold()
            child_names = {name.casefold() for name in children}
            file_names = {name.casefold() for name in files}
            has_source_layout = "src" in child_names or any(
                name.endswith(".java") for name in file_names
            )
            has_git_metadata = ".git" in child_names or ".git" in file_names
            for seed, repository_name in repository_names.items():
                candidate_names = {
                    seed.family_id.casefold(),
                    repository_name,
                    f"{repository_name}-{seed.version}".casefold(),
                    f"{seed.family_id}-{seed.version}".casefold(),
                }
                if directory_name in candidate_names and has_git_metadata:
                    record(seed, cache_class, "SCM_CHECKOUT_DIRECTORY_NAME_PRESENT")
                elif directory_name in candidate_names and has_source_layout:
                    record(seed, cache_class, "EXTRACTED_SOURCE_ROOT_NAME_PRESENT")
            for name in sorted(files):
                lowered = name.casefold()
                seed = source_names.get(lowered)
                if seed is not None:
                    record(seed, cache_class, "EXACT_SOURCE_JAR_FILENAME_PRESENT")
                    continue
                if not lowered.endswith((".zip", ".tar", ".tar.gz", ".tgz")):
                    continue
                for candidate, repository_name in repository_names.items():
                    identity_tokens = (
                        candidate.family_id.casefold(),
                        repository_name,
                        candidate.version.casefold(),
                        candidate.scm_ref.rsplit("/", 1)[-1].casefold(),
                    )
                    if any(
                        token and token in lowered for token in identity_tokens[:2]
                    ) and any(
                        token and token in lowered for token in identity_tokens[2:]
                    ):
                        record(
                            candidate,
                            cache_class,
                            "SCM_ARCHIVE_FILENAME_PRESENT",
                        )
    ordered = tuple(rows_by_key[key] for key in sorted(rows_by_key))
    body = {
        "schema_version": 1,
        "platform": platform,
        "candidate_count": len(seeds),
        "inspected_root_classes": tuple(sorted({item[0] for item in roots})),
        "source_body_bytes_read": 0,
        "matches": ordered,
        "excluded_family_ids": tuple(sorted({item["family_id"] for item in ordered})),
    }
    return {**body, "receipt_hash": content_hash(body)}


def probe_metadata_pool(
    *, windows_cache: dict, karina_cache: dict, timestamp: str, host: str
) -> tuple[dict, dict, dict]:
    """Probe POM/HEAD/checksum/ref metadata without reading a source-JAR body."""

    excluded = set(windows_cache["excluded_family_ids"]) | set(
        karina_cache["excluded_family_ids"]
    )
    candidates = []
    network_receipts = []
    failures = []
    for seed in frozen_candidate_seeds():
        if seed.family_id in excluded:
            continue
        try:
            row, receipts = _probe_one(seed, timestamp=timestamp, host=host)
        except Exception as exc:  # noqa: BLE001 - every failed identity is evidence
            failures.append(
                {
                    "family_id": seed.family_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                    "failure_hash": content_hash(
                        (seed.family_id, type(exc).__name__, str(exc)[:240])
                    ),
                }
            )
            continue
        candidates.append(row)
        network_receipts.extend(receipts)
    candidates = tuple(sorted(candidates, key=lambda item: item["family_id"]))
    organizations = Counter(item["organization_id"] for item in candidates)
    if (
        len(candidates) < 24
        or len(organizations) < 16
        or max(organizations.values()) > 2
    ):
        raise ValueError("actual metadata pool misses the frozen size/diversity bounds")
    if any(item["requirement"] != "OPTIONAL" for item in candidates):
        raise ValueError("final candidates must all be optional")
    body = {
        "schema_version": 1,
        "policy_version": M336D_METADATA_POLICY_VERSION,
        "candidate_count": len(candidates),
        "organization_count": len(organizations),
        "maximum_candidates_per_organization": max(organizations.values()),
        "required_candidate_count": 0,
        "optional_candidate_count": len(candidates),
        "pre_f19_source_body_bytes_received": 0,
        "candidates": candidates,
        "failed_seed_receipt_hashes": tuple(
            sorted(item["failure_hash"] for item in failures)
        ),
    }
    pool = {**body, "pool_hash": content_hash(body)}
    receipt_body = {
        "schema_version": 1,
        "request_count": len(network_receipts),
        "source_jar_get_count": 0,
        "source_jar_head_count": len(candidates),
        "source_body_bytes_received": 0,
        "receipts": tuple(
            sorted(network_receipts, key=lambda item: item["receipt_hash"])
        ),
        "failures": tuple(sorted(failures, key=lambda item: item["family_id"])),
    }
    receipts = {**receipt_body, "report_hash": content_hash(receipt_body)}
    scenarios = _failure_scenarios(
        candidates,
        locally_excluded=tuple(sorted(excluded)),
    )
    return pool, receipts, scenarios


def validate_candidate_pool(pool: dict) -> tuple[dict, ...]:
    body = dict(pool)
    claimed = body.pop("pool_hash")
    if content_hash(body) != claimed or pool.get("schema_version") != 1:
        raise ValueError("candidate pool hash/schema mismatch")
    candidates = tuple(pool["candidates"])
    organizations = Counter(item["organization_id"] for item in candidates)
    families = tuple(item["family_id"] for item in candidates)
    if (
        len(candidates) < 24
        or len(organizations) < 16
        or max(organizations.values()) > 2
        or len(families) != len(set(families))
        or any(item["requirement"] != "OPTIONAL" for item in candidates)
        or pool["pre_f19_source_body_bytes_received"] != 0
    ):
        raise ValueError("candidate pool cardinality/freshness policy mismatch")
    for item in candidates:
        candidate_body = dict(item)
        policy_hash = candidate_body.pop("policy_hash")
        if content_hash(candidate_body) != policy_hash:
            raise ValueError("candidate policy hash mismatch")
    seed_ids = {item.family_id for item in frozen_candidate_seeds()}
    if set(families) - seed_ids:
        raise ValueError("candidate pool contains an identity outside frozen seeds")
    return candidates


def acquire_qualify_select_once(
    *,
    pool: dict,
    vault_root: Path,
    public_output: Path,
    authority_statement: Path,
    f19_sha: str,
    timestamp: str,
    host: str,
    git_worktrees: tuple[Path, ...],
) -> dict:
    """Perform the only source-body acquisition and exactly one global selection."""

    if not _GIT_SHA.fullmatch(f19_sha):
        raise ValueError("acquisition requires exact F19 SHA")
    tracemalloc.start()
    acquisition_started = time.perf_counter()
    candidates = validate_candidate_pool(pool)
    if vault_root.exists() or public_output.exists():
        raise FileExistsError("fresh one-shot acquisition targets must not exist")
    vault_root.mkdir(parents=True)
    LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY.validate_root(
        vault_root, git_worktrees=git_worktrees
    )
    public_output.mkdir(parents=True)
    maven = MavenCentralProvenanceProvider(timeout_seconds=180)
    scm = ScmRevisionProvider(timeout_seconds=240)
    acquired = []
    performance_samples: dict[str, list[float]] = {}
    vault_files: list[tuple[str, str, LocalVaultRole, str]] = []
    for policy in candidates:
        acquired.append(
            _acquire_one(policy, vault_root=vault_root, maven=maven, scm=scm)
        )
        vault_files.extend(acquired[-1].pop("_vault_files"))
        for name, seconds in acquired[-1].pop("_performance_seconds").items():
            performance_samples.setdefault(name, []).append(seconds)
    content_rows = tuple(
        sorted(
            (
                relative,
                bytes_hash((vault_root / relative).read_bytes()),
                role.value,
                parent,
                family,
            )
            for relative, family, role, parent in vault_files
        )
    )
    vault_content_manifest_hash = content_hash(content_rows)
    authority_load_started = time.perf_counter()
    registry = load_pinned_authority_registry_for_development(
        authority_statement,
        expected_statement_sha256=M336D_AUTHORITY_STATEMENT_SHA256,
    )
    performance_samples["authority_root_load"] = [
        time.perf_counter() - authority_load_started
    ]
    authorization_by_family = {}
    authority_verification_started = time.perf_counter()
    for item in acquired:
        binding = SourceAuthorizationBinding(
            f19_sha=f19_sha,
            acquisition_run_id=M336D_ACQUISITION_RUN_ID,
            candidate_family_id=item["family_id"],
            maven_coordinate=item["coordinate"],
            source_repository_url=item["source_url"],
            source_jar_sha256=item["source_jar_sha256"],
            pom_sha256=item["pom_sha256"],
            immutable_scm_commit=item["immutable_scm_commit"],
            scm_archive_sha256=item["scm_archive_sha256"],
            source_tree_hash=item["source_tree_hash"],
            local_vault_manifest_hash=vault_content_manifest_hash,
        )
        receipt = registry.issue(
            binding,
            source_use_scopes=(
                SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
                SourceUseScope.LOCAL_RESEARCH_EVALUATION,
                SourceUseScope.DERIVED_KNOWLEDGE_ONLY,
                SourceUseScope.RAW_SOURCE_RETENTION,
                SourceUseScope.PUBLIC_REPRODUCIBLE_EVALUATION,
            ),
            publication_targets=(
                PublicationTarget.DERIVED_PACK_PUBLICATION,
                PublicationTarget.METRICS_ONLY_PUBLICATION,
            ),
        )
        registry.verify(receipt, expected_binding=binding)
        authorization_by_family[item["family_id"]] = receipt
        item["authority"] = receipt_public_dict(receipt)
        item["authority_receipt_hash"] = receipt.receipt_hash
    performance_samples["authority_receipt_verification"] = [
        time.perf_counter() - authority_verification_started
    ]
    bindings = {
        relative: (
            family,
            role,
            parent,
            authorization_by_family[family].receipt_hash,
        )
        for relative, family, role, parent in vault_files
    }
    vault_seal_started = time.perf_counter()
    _set_read_only(vault_root)
    manifest = LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY.build_manifest(
        vault_root,
        bindings=bindings,
        git_worktrees=git_worktrees,
        f19_sha=f19_sha,
        acquisition_run_id=M336D_ACQUISITION_RUN_ID,
        seal_timestamp=timestamp,
    )
    LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY.verify_manifest(
        vault_root, manifest, git_worktrees=git_worktrees
    )
    performance_samples["vault_sealing"] = [time.perf_counter() - vault_seal_started]
    disclosed = load_disclosed_java_registry()
    for item in acquired:
        overlap_counts = _candidate_overlap_counts(item, disclosed)
        item["preselection_overlap_counts"] = overlap_counts
        if sum(overlap_counts.values()):
            item["analysis_eligible"] = False
            item["qualification_errors"] = (
                *item["qualification_errors"],
                "FRESHNESS:DISCLOSED_IDENTITY_OVERLAP",
            )
    selection_sentinel = vault_root.parent / f"{vault_root.name}.selector-invoked"
    if selection_sentinel.exists():
        raise FileExistsError("selector already invoked for this sealed vault")
    selection_sentinel.write_text(
        manifest.manifest_hash + "\n", encoding="ascii", newline="\n"
    )
    selector_started = time.perf_counter()
    selected, selector = _select_once(acquired, vault_root, f19_sha=f19_sha)
    performance_samples["selector"] = [time.perf_counter() - selector_started]
    qualification = _qualification_report(acquired)
    acquisition = _acquisition_report(acquired, f19_sha=f19_sha, host=host)
    overlap = _overlap_report(acquired, selected)
    disclosure_append = _disclosure_append(acquired, selected)
    public_manifest = _public_vault_manifest(manifest, vault_content_manifest_hash)
    _write_json(public_output / "acquisition_receipts.json", acquisition)
    _write_json(public_output / "qualification_decisions.json", qualification)
    _write_json(public_output / "selector_receipt.json", selector)
    _write_json(public_output / "selected_source_manifest.json", selected)
    _write_json(public_output / "source_overlap.json", overlap)
    _write_json(public_output / "disclosure_registry_append.json", disclosure_append)
    _write_json(public_output / "vault_manifest.json", public_manifest)
    total_seconds = time.perf_counter() - acquisition_started
    _current_python_bytes, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    performance_body = {
        "schema_version": 1,
        "platform": "windows",
        "operation_count": len(performance_samples),
        "operations": tuple(
            (name, _performance_summary(samples))
            for name, samples in sorted(performance_samples.items())
        ),
        "total_acquisition_seconds": f"{total_seconds:.6f}",
        "throughput_candidates_per_second": f"{len(candidates) / total_seconds:.6f}",
        "peak_python_bytes": peak_python_bytes,
    }
    _write_json(
        public_output / "acquisition_performance.json",
        {**performance_body, "report_hash": content_hash(performance_body)},
    )
    return {
        "acquisition": acquisition,
        "qualification": qualification,
        "selector": selector,
        "selected": selected,
        "overlap": overlap,
        "disclosure_append": disclosure_append,
        "vault_manifest": public_manifest,
    }


def verify_vault_copy(
    root: Path, public_manifest: dict, *, git_worktrees: tuple[Path, ...]
) -> dict:
    manifest_body = dict(public_manifest)
    claimed_manifest_hash = manifest_body.pop("manifest_hash")
    if content_hash(manifest_body) != claimed_manifest_hash or not _GIT_SHA.fullmatch(
        public_manifest.get("f19_sha", "")
    ):
        raise ValueError("public vault manifest hash/F19 binding mismatch")
    for row in public_manifest["rows"]:
        row_body = {
            "candidate_id": row["candidate_id"],
            "relative_canonical_path": row["relative_path"],
            "role": row["role"],
            "byte_size": row["byte_size"],
            "sha256": row["sha256"],
            "parent_artifact_identity": row["parent_artifact_hash"],
            "source_use_receipt_hash": row["source_use_receipt_hash"],
        }
        if content_hash(row_body) != row["row_hash"]:
            raise ValueError("public vault row hash mismatch")
    LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY.validate_root(
        root, git_worktrees=git_worktrees
    )
    vault_paths = tuple(
        sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode(),
        )
    )
    if any(
        path.is_symlink()
        or bool(
            getattr(path.stat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        for path in vault_paths
    ):
        raise ValueError("vault copy contains a link/reparse point")
    rows = tuple(
        (
            path.relative_to(root).as_posix(),
            bytes_hash(path.read_bytes()),
            path.stat().st_size,
        )
        for path in vault_paths
    )
    expected = tuple(
        (item["relative_path"], item["sha256"], item["byte_size"])
        for item in public_manifest["rows"]
    )
    body = {
        "schema_version": 1,
        "file_count_equal": len(rows) == public_manifest["file_count"],
        "all_file_hashes_equal": rows == expected,
        "tree_hash_equal": content_hash(tuple((a, b) for a, b, _c in rows))
        == public_manifest["tree_hash"],
        "all_files_write_protected": all(
            not bool(path.stat().st_mode & stat.S_IWUSR) for path in vault_paths
        ),
    }
    body["difference_count"] = 0 if all(body.values()) else 1
    return {**body, "report_hash": content_hash(body)}


def materialize_selected_sources(
    vault_root: Path, selected_manifest: dict, target: Path
) -> tuple[Path, ...]:
    if target.exists():
        raise FileExistsError("selected source materialization target exists")
    target.mkdir(parents=True)
    copied = []
    for row in selected_manifest["files"]:
        source = vault_root / row["vault_relative_path"]
        raw = source.read_bytes()
        if bytes_hash(raw) != row["source_sha256"]:
            raise ValueError("selected source hash mismatch")
        destination = target / row["family_id"] / row["source_relative_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        copied.append(destination)
    return tuple(copied)


def _probe_one(seed: CandidateSeed, *, timestamp: str, host: str):
    coordinate = maven_coordinate(
        group_id=seed.group_id, artifact_id=seed.artifact_id, version=seed.version
    )
    source_url = f"{coordinate.repository}/{coordinate.canonical_repository_path}"
    pom_url = source_url.rsplit("/", 1)[0] + f"/{seed.artifact_id}-{seed.version}.pom"
    pom, pom_receipt = _http("GET", pom_url, timestamp=timestamp, host=host)
    _head, source_receipt = _http("HEAD", source_url, timestamp=timestamp, host=host)
    sidecar, sidecar_receipt = _http_optional(
        "GET", source_url + ".sha256", timestamp=timestamp, host=host
    )
    _signature, signature_receipt = _http_optional(
        "HEAD", source_url + ".asc", timestamp=timestamp, host=host
    )
    command = (
        "git",
        "ls-remote",
        seed.scm_repository,
        seed.scm_ref,
        f"{seed.scm_ref}^{{}}",
    )
    completed = subprocess.run(command, check=True, capture_output=True, timeout=90)
    commits = {}
    for line in completed.stdout.decode("ascii", errors="strict").splitlines():
        sha, ref = line.split("\t", 1)
        if not _GIT_SHA.fullmatch(sha) or ref not in {
            seed.scm_ref,
            f"{seed.scm_ref}^{{}}",
        }:
            raise ValueError("git ls-remote returned an unexpected row")
        commits[ref] = sha
    if seed.scm_ref not in commits:
        raise ValueError("frozen SCM ref did not resolve")
    commit = commits.get(f"{seed.scm_ref}^{{}}", commits[seed.scm_ref])
    pom_evidence = parse_maven_pom(pom, coordinate)
    sidecar_value = _sidecar_value(sidecar) if sidecar is not None else None
    git_body = {
        "requested_url": seed.scm_repository,
        "method": "GIT_LS_REMOTE",
        "final_url": seed.scm_repository,
        "redirects": (),
        "response_status": 0,
        "relevant_headers": (),
        "bytes_received": len(completed.stdout),
        "timestamp": timestamp,
        "host": host,
        "request_hash": content_hash(command),
        "response_hash": bytes_hash(completed.stdout),
    }
    git_receipt = {**git_body, "receipt_hash": content_hash(git_body)}
    row_body = {
        "family_id": seed.family_id,
        "organization_id": seed.organization_id,
        "group_id": seed.group_id,
        "artifact_id": seed.artifact_id,
        "version": seed.version,
        "coordinate": f"{seed.group_id}:{seed.artifact_id}:{seed.version}",
        "requirement": "OPTIONAL",
        "source_url": source_url,
        "pom_url": pom_url,
        "metadata_pom_sha256": bytes_hash(pom),
        "packaging": _pom_packaging(pom),
        "pom_license_declarations": tuple(
            sorted(
                (
                    claim.spdx_identifier,
                    claim.declared_name,
                    claim.declaration_hash,
                )
                for claim in pom_evidence.licenses
            )
        ),
        "pom_scm_metadata": tuple(
            value
            for value in (
                pom_evidence.scm_connection,
                pom_evidence.scm_url,
                pom_evidence.scm_tag,
            )
            if value
        ),
        "declared_java_releases": _pom_declared_java_releases(pom),
        "source_content_length": int(
            dict(source_receipt["relevant_headers"])["content-length"]
        ),
        "source_sha256_sidecar_available": sidecar is not None,
        "source_sha256_sidecar_value": sidecar_value,
        "source_signature_available": signature_receipt["response_status"] == 200,
        "scm_repository": seed.scm_repository,
        "scm_ref": seed.scm_ref,
        "scm_commit": commit,
        "repository_source_prefixes": seed.repository_source_prefixes,
        "metadata_receipt_hashes": tuple(
            sorted(
                item["receipt_hash"]
                for item in (
                    pom_receipt,
                    source_receipt,
                    sidecar_receipt,
                    signature_receipt,
                    git_receipt,
                )
            )
        ),
    }
    row = {**row_body, "policy_hash": content_hash(row_body)}
    return row, (
        pom_receipt,
        source_receipt,
        sidecar_receipt,
        signature_receipt,
        git_receipt,
    )


def _http(method: str, url: str, *, timestamp: str, host: str):
    redirects: list[str] = []
    opener = urllib.request.build_opener(_MetadataRedirectHandler(redirects))
    request = urllib.request.Request(
        url, method=method, headers={"User-Agent": "ai-brain-m336d-metadata/1"}
    )
    with opener.open(request, timeout=60) as response:
        raw = response.read() if method == "GET" else b""
        headers = tuple(
            sorted(
                (name.casefold(), response.headers.get(name))
                for name in ("Content-Length", "Content-Type", "ETag", "Last-Modified")
                if response.headers.get(name) is not None
            )
        )
        final_url = response.geturl()
        status = response.status
    body = {
        "requested_url": url,
        "method": method,
        "final_url": final_url,
        "redirects": tuple(redirects),
        "response_status": status,
        "relevant_headers": headers,
        "bytes_received": len(raw),
        "timestamp": timestamp,
        "host": host,
        "request_hash": content_hash((method, url)),
        "response_hash": bytes_hash(raw) if method == "GET" else content_hash(headers),
    }
    return raw, {**body, "receipt_hash": content_hash(body)}


def _http_optional(method: str, url: str, *, timestamp: str, host: str):
    try:
        return _http(method, url, timestamp=timestamp, host=host)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        body = {
            "requested_url": url,
            "method": method,
            "final_url": url,
            "redirects": (),
            "response_status": 404,
            "relevant_headers": (),
            "bytes_received": 0,
            "timestamp": timestamp,
            "host": host,
            "request_hash": content_hash((method, url)),
            "response_hash": bytes_hash(b""),
        }
        return None, {**body, "receipt_hash": content_hash(body)}


def _acquire_one(policy, *, vault_root: Path, maven, scm):
    family = policy["family_id"]
    root = vault_root / "candidates" / family
    root.mkdir(parents=True)
    coordinate = maven_coordinate(
        group_id=policy["group_id"],
        artifact_id=policy["artifact_id"],
        version=policy["version"],
    )
    errors = []
    source = pom = revision = inspection = correspondence = inventory = None
    vault_files = []
    performance = {}
    source_started = time.perf_counter()
    try:
        source = maven.fetch_sources(coordinate)
        if len(source.payload) != policy["source_content_length"]:
            raise ValueError("source size changed after F19")
        if (
            source.digest.sidecar_verified
            is not policy["source_sha256_sidecar_available"]
        ):
            raise ValueError("source sidecar availability changed after F19")
        if (
            policy["source_sha256_sidecar_value"] is not None
            and source.digest.downloaded_bytes_sha256
            != policy["source_sha256_sidecar_value"]
        ):
            raise ValueError("source SHA-256 changed after F19")
        if (source.digest.detached_signature_url is not None) is not policy[
            "source_signature_available"
        ]:
            raise ValueError("source signature availability changed after F19")
        path = root / "source.jar"
        path.write_bytes(source.payload)
        vault_files.append(
            (
                _relative(vault_root, path),
                family,
                LocalVaultRole.SOURCE_JAR,
                content_hash(policy["coordinate"]),
            )
        )
        inspection = inspect_source_archive(source.payload)
        sources = root / "sources"
        sources.mkdir()
        for relative, raw in inspection.java_entries:
            destination = sources.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            vault_files.append(
                (
                    _relative(vault_root, destination),
                    family,
                    LocalVaultRole.JAVA_SOURCE,
                    source.digest.downloaded_bytes_sha256,
                )
            )
    except Exception as exc:  # noqa: BLE001 - candidate-local acquisition failure
        errors.append(f"SOURCE:{type(exc).__name__}:{str(exc)[:160]}")
    performance["source_acquisition"] = time.perf_counter() - source_started
    pom_started = time.perf_counter()
    try:
        pom = maven.fetch_pom(coordinate)
        if bytes_hash(pom.payload) != policy["metadata_pom_sha256"]:
            raise ValueError("POM changed after F19")
        path = root / "pom.xml"
        path.write_bytes(pom.payload)
        vault_files.append(
            (
                _relative(vault_root, path),
                family,
                LocalVaultRole.POM,
                content_hash(policy["coordinate"]),
            )
        )
    except Exception as exc:  # noqa: BLE001 - candidate-local acquisition failure
        errors.append(f"POM:{type(exc).__name__}:{str(exc)[:160]}")
    performance["pom_acquisition"] = time.perf_counter() - pom_started
    scm_started = time.perf_counter()
    try:
        revision = scm.verify(
            repository_url=policy["scm_repository"], requested_ref=policy["scm_ref"]
        )
        if revision.receipt.immutable_commit != policy["scm_commit"]:
            raise ValueError("SCM tag moved after F19")
        path = root / "scm.zip"
        path.write_bytes(revision.archive_payload)
        vault_files.append(
            (
                _relative(vault_root, path),
                family,
                LocalVaultRole.SCM_ARCHIVE,
                content_hash(policy["scm_commit"]),
            )
        )
    except Exception as exc:  # noqa: BLE001 - candidate-local acquisition failure
        errors.append(f"SCM:{type(exc).__name__}:{str(exc)[:160]}")
    performance["scm_acquisition"] = time.perf_counter() - scm_started
    if inspection is not None and revision is not None:
        correspondence_started = time.perf_counter()
        try:
            correspondence = correspond_source_trees(
                inspection.java_entries,
                revision.java_entries,
                repository_path_prefixes=tuple(policy["repository_source_prefixes"]),
            )
        except Exception as exc:  # noqa: BLE001 - candidate-local qualification
            errors.append(f"CORRESPONDENCE:{type(exc).__name__}:{str(exc)[:160]}")
        performance["source_correspondence"] = (
            time.perf_counter() - correspondence_started
        )
    if inspection is not None and revision is not None and correspondence is not None:
        inventory_started = time.perf_counter()
        try:
            inventory = inventory_legal_documents(
                (
                    LegalDocumentContainer("source-jar", source.payload),
                    LegalDocumentContainer("scm-archive", revision.archive_payload),
                )
            )
            legal_root = root / "legal"
            for container_id, archive_raw in (
                ("source-jar", source.payload),
                ("scm-archive", revision.archive_payload),
            ):
                with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
                    wanted = {
                        item.path
                        for item in inventory.rows
                        if item.container_id == container_id
                    }
                    prefix = (
                        ""
                        if container_id == "source-jar"
                        else _zip_root_prefix(archive)
                    )
                    for relative in sorted(wanted):
                        raw = archive.read(prefix + relative)
                        destination = (
                            legal_root / container_id / PurePosixPath(relative)
                        )
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(raw)
                        vault_files.append(
                            (
                                _relative(vault_root, destination),
                                family,
                                LocalVaultRole.LEGAL_DOCUMENT,
                                bytes_hash(archive_raw),
                            )
                        )
        except Exception as exc:  # noqa: BLE001 - candidate-local qualification
            errors.append(f"LEGAL_INVENTORY:{type(exc).__name__}:{str(exc)[:160]}")
        performance["legal_document_inventory"] = (
            time.perf_counter() - inventory_started
        )
    qualification_started = time.perf_counter()
    source_hash = source.digest.downloaded_bytes_sha256 if source else "0" * 64
    pom_hash = bytes_hash(pom.payload) if pom else "0" * 64
    scm_hash = bytes_hash(revision.archive_payload) if revision else "0" * 64
    commit = revision.receipt.immutable_commit if revision else "0" * 40
    tree_hash = revision.receipt.source_tree_hash if revision else "0" * 64
    complete_entries = tuple(
        item.artifact_path
        for item in (correspondence.entries if correspondence else ())
        if item.status in _COMPLETE
    )
    all_correspond = bool(
        correspondence
        and not correspondence.unmatched_count
        and not correspondence.ambiguous_count
    )
    auto_licenses = tuple(
        sorted(
            {
                item.spdx_license_id
                for item in (inventory.rows if inventory else ())
                if item.spdx_license_id
            }
        )
    )
    expression_started = time.perf_counter()
    for expression in auto_licenses:
        if parse_spdx_expression(expression).canonical() != expression:
            errors.append("LICENSE:NONCANONICAL_SPDX_EXPRESSION")
    performance["expression_parsing"] = time.perf_counter() - expression_started
    if inventory is not None and (
        inventory.unclassified_document_count or inventory.unknown_role_count
    ):
        errors.append(
            "LICENSE:UNKNOWN_LICENSE_DOCUMENT:"
            f"unclassified={inventory.unclassified_document_count},"
            f"unknown_role={inventory.unknown_role_count}"
        )
    raw_source_hashes = tuple(
        sorted(
            bytes_hash(raw)
            for _path, raw in (inspection.java_entries if inspection else ())
        )
    )
    canonical_source_hashes = tuple(
        sorted(
            bytes_hash(canonical_source_bytes(raw))
            for _path, raw in (inspection.java_entries if inspection else ())
        )
    )
    eligible = bool(
        source
        and pom
        and revision
        and complete_entries
        and auto_licenses
        and inventory is not None
        and inventory.unclassified_document_count == 0
        and inventory.unknown_role_count == 0
        and not errors
    )
    public_correspondence = (
        asdict(derive_scm_correspondence_decision(correspondence, selected_paths=()))
        if correspondence
        else None
    )
    performance["candidate_qualification"] = time.perf_counter() - qualification_started
    return {
        "family_id": family,
        "organization_id": policy["organization_id"],
        "coordinate": policy["coordinate"],
        "source_url": policy["source_url"],
        "source_jar_sha256": source_hash,
        "source_jar_size": len(source.payload) if source else 0,
        "pom_sha256": pom_hash,
        "immutable_scm_commit": commit,
        "scm_archive_sha256": scm_hash,
        "scm_archive_size": len(revision.archive_payload) if revision else 0,
        "source_tree_hash": tree_hash,
        "artifact_authenticity_mode": "MAVEN_CENTRAL_PLUS_IMMUTABLE_SCM"
        if source and revision
        else "INCOMPLETE",
        "scoped_license_expressions": auto_licenses,
        "legal_document_count": inventory.discovered_document_count if inventory else 0,
        "unclassified_legal_document_count": inventory.unclassified_document_count
        if inventory
        else 0,
        "unknown_legal_document_role_count": inventory.unknown_role_count
        if inventory
        else 0,
        "correspondence": public_correspondence,
        "correspondence_complete_for_all_entries": all_correspond,
        "complete_correspondence_paths": complete_entries,
        "analysis_eligible": eligible,
        "candidate_eligible_source_entry_count": len(complete_entries)
        if eligible
        else 0,
        "qualification_errors": tuple(errors),
        "_raw_source_hashes": raw_source_hashes,
        "_canonical_source_hashes": canonical_source_hashes,
        # Private acquisition facts retained for the M-33.6e file-scoped
        # qualification pass. They are never emitted by the M-33.6d producer.
        "_archive_java_paths": tuple(
            path for path, _raw in (inspection.java_entries if inspection else ())
        ),
        "_legal_inventory_rows": tuple(inventory.rows) if inventory else (),
        "_vault_files": vault_files,
        "_performance_seconds": performance,
    }


def _select_once(acquired: list[dict], vault_root: Path, *, f19_sha: str):
    ranked: dict[str, list[tuple[str, str, Path]]] = {}
    for item in acquired:
        if not item["analysis_eligible"]:
            continue
        family = item["family_id"]
        rows = []
        for relative in item["complete_correspondence_paths"]:
            pure = PurePosixPath(relative)
            if {part.casefold() for part in pure.parts} & {
                "test",
                "tests",
                "generated",
                "vendor",
            }:
                continue
            if pure.name in {"module-info.java", "package-info.java"}:
                continue
            path = vault_root / "candidates" / family / "sources" / pure
            raw = path.read_bytes()
            try:
                callable_source = _contains_real_callable_type(raw)
            except Exception:  # noqa: BLE001 - malformed candidates are excluded
                callable_source = False
            if callable_source:
                rows.append(
                    (
                        content_hash(
                            (
                                f19_sha,
                                M336D_SELECTOR_SEED,
                                family,
                                relative,
                                bytes_hash(raw),
                            )
                        ),
                        relative,
                        path,
                    )
                )
        if rows:
            ranked[family] = sorted(rows)
    if len(ranked) < 3:
        raise ValueError("fewer than three qualified roots have callable Java sources")
    cap = int(M336D_SELECTED_FILE_COUNT * float(M336D_MAXIMUM_ROOT_FRACTION))
    selected = []
    counts = Counter()
    while len(selected) < M336D_SELECTED_FILE_COUNT:
        progressed = False
        for family in sorted(ranked):
            if len(selected) >= M336D_SELECTED_FILE_COUNT:
                break
            if counts[family] >= cap or not ranked[family]:
                continue
            _rank, relative, path = ranked[family].pop(0)
            raw = path.read_bytes()
            selected.append(
                {
                    "family_id": family,
                    "source_relative_path": relative,
                    "vault_relative_path": _relative(vault_root, path),
                    "source_sha256": bytes_hash(raw),
                    "canonical_source_sha256": bytes_hash(canonical_source_bytes(raw)),
                    "byte_size": len(raw),
                }
            )
            counts[family] += 1
            progressed = True
        if not progressed:
            break
    if len(selected) != M336D_SELECTED_FILE_COUNT or len(counts) < 3:
        raise ValueError("frozen selector cannot satisfy exact 180-file/3-root policy")
    if max(counts.values()) / len(selected) > float(M336D_MAXIMUM_ROOT_FRACTION):
        raise ValueError("selected root exceeds frozen 35 percent cap")
    files = tuple(selected)
    selected_body = {
        "schema_version": 1,
        "file_count": len(files),
        "root_count": len(counts),
        "root_distribution": tuple(sorted(counts.items())),
        "files": files,
    }
    selected_manifest = {**selected_body, "manifest_hash": content_hash(selected_body)}
    selector_body = {
        "schema_version": 1,
        "selector_version": M336D_SELECTOR_VERSION,
        "selector_seed": M336D_SELECTOR_SEED,
        "f19_sha": f19_sha,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "selected_file_count": len(files),
        "selected_root_count": len(counts),
        "maximum_one_root_fraction": f"{max(counts.values()) / len(files):.6f}",
        "metrics_used_count": 0,
        "oracle_golden_read_count": 0,
        "selected_manifest_hash": selected_manifest["manifest_hash"],
        "root_distribution": tuple(sorted(counts.items())),
    }
    return selected_manifest, {
        **selector_body,
        "receipt_hash": content_hash(selector_body),
    }


def _qualification_report(acquired):
    decisions = []
    for item in sorted(acquired, key=lambda value: value["family_id"]):
        authority = item["authority"]
        source_scopes = set(authority["permitted_source_use_scopes"])
        publication_targets = set(authority["permitted_publication_targets"])
        denied_targets = set(authority["denied_publication_targets"])
        authentic = (
            item["artifact_authenticity_mode"] == "MAVEN_CENTRAL_PLUS_IMMUTABLE_SCM"
            and item["source_jar_sha256"] != "0" * 64
            and item["pom_sha256"] != "0" * 64
            and item["scm_archive_sha256"] != "0" * 64
            and item["immutable_scm_commit"] != "0" * 40
        )
        correspondence_complete = item["correspondence_complete_for_all_entries"]
        license_resolved = bool(item["scoped_license_expressions"]) and not (
            item["unclassified_legal_document_count"]
            or item["unknown_legal_document_role_count"]
        )
        freshness_clear = not sum(item.get("preselection_overlap_counts", {}).values())
        eligible = bool(
            item["analysis_eligible"]
            and authentic
            and correspondence_complete
            and license_resolved
            and freshness_clear
        )
        retention_allowed = SourceUseScope.RAW_SOURCE_RETENTION.value in source_scopes
        raw_denied = PublicationTarget.RAW_SOURCE_PUBLICATION.value in denied_targets
        excerpt_denied = (
            PublicationTarget.SOURCE_EXCERPT_PUBLICATION.value in denied_targets
        )
        derived_allowed = (
            PublicationTarget.DERIVED_PACK_PUBLICATION.value in publication_targets
            and eligible
        )
        metrics_allowed = (
            PublicationTarget.METRICS_ONLY_PUBLICATION.value in publication_targets
        )
        body = {
            "family_id": item["family_id"],
            "organization_id": item["organization_id"],
            "coordinate": item["coordinate"],
            "source_authenticity_decision": "AUTHENTIC"
            if authentic
            else "REVIEW_REQUIRED",
            "knowledge_acquisition_eligibility_decision": "ELIGIBLE_FOR_ANALYSIS"
            if eligible
            else "INELIGIBLE",
            "source_retention_decision": "ALLOWED_SEALED_VAULT_ONLY"
            if retention_allowed
            else "DENIED",
            "raw_source_publication_decision": "DENIED"
            if raw_denied
            else "NOT_AUTHORIZED",
            "source_excerpt_publication_decision": "DENIED"
            if excerpt_denied
            else "NOT_AUTHORIZED",
            "derived_pack_publication_decision": "ALLOWED"
            if derived_allowed
            else "NOT_APPLICABLE",
            "metrics_publication_decision": "ALLOWED"
            if metrics_allowed
            else "NOT_AUTHORIZED",
            "scm_correspondence_decision": "COMPLETE"
            if correspondence_complete
            else "INCOMPLETE",
            "scoped_license_decision": "RESOLVED"
            if license_resolved
            else "REVIEW_REQUIRED",
            "candidate_eligible_source_set_count": item[
                "candidate_eligible_source_entry_count"
            ],
            "scoped_license_expressions": item["scoped_license_expressions"],
            "legal_document_count": item["legal_document_count"],
            "unclassified_legal_document_count": item[
                "unclassified_legal_document_count"
            ],
            "authority_receipt_hash": item["authority_receipt_hash"],
            "authority": item["authority"],
            "qualification_errors": item["qualification_errors"],
        }
        decisions.append({**body, "decision_hash": content_hash(body)})
    eligible = tuple(
        item
        for item in decisions
        if item["knowledge_acquisition_eligibility_decision"] == "ELIGIBLE_FOR_ANALYSIS"
    )
    body = {
        "schema_version": 1,
        "candidate_count": len(decisions),
        "analysis_eligible_root_count": len(eligible),
        "analysis_eligible_java_entry_count": sum(
            item["candidate_eligible_source_set_count"] for item in eligible
        ),
        "raw_source_publication_root_count": sum(
            item["raw_source_publication_decision"] == "ALLOWED" for item in decisions
        ),
        "source_excerpt_publication_root_count": sum(
            item["source_excerpt_publication_decision"] == "ALLOWED"
            for item in decisions
        ),
        "derived_pack_publication_root_count": sum(
            item["derived_pack_publication_decision"] == "ALLOWED"
            and item["knowledge_acquisition_eligibility_decision"]
            == "ELIGIBLE_FOR_ANALYSIS"
            for item in decisions
        ),
        "metrics_publication_root_count": sum(
            item["metrics_publication_decision"] == "ALLOWED"
            and item["knowledge_acquisition_eligibility_decision"]
            == "ELIGIBLE_FOR_ANALYSIS"
            for item in decisions
        ),
        "typed_decisions_per_candidate": 10,
        "decisions": tuple(decisions),
    }
    return {**body, "report_hash": content_hash(body)}


def _acquisition_report(acquired, *, f19_sha: str, host: str):
    receipts = tuple(
        {
            "family_id": item["family_id"],
            "coordinate": item["coordinate"],
            "source_url": item["source_url"],
            "source_jar_sha256": item["source_jar_sha256"],
            "source_jar_size": item["source_jar_size"],
            "pom_sha256": item["pom_sha256"],
            "immutable_scm_commit": item["immutable_scm_commit"],
            "scm_archive_sha256": item["scm_archive_sha256"],
            "scm_archive_size": item["scm_archive_size"],
            "source_tree_hash": item["source_tree_hash"],
            "authority_receipt_hash": item["authority_receipt_hash"],
        }
        for item in sorted(acquired, key=lambda value: value["family_id"])
    )
    body = {
        "schema_version": 1,
        "f19_sha": f19_sha,
        "acquisition_run_id": M336D_ACQUISITION_RUN_ID,
        "global_acquisition_count": 1,
        "candidate_count": len(receipts),
        "host_audit_hash": content_hash(host),
        "receipts": receipts,
    }
    return {**body, "report_hash": content_hash(body)}


def _candidate_overlap_counts(item, disclosed, *, selected_paths=()):
    labels = (
        "coordinate",
        "family",
        "source_url",
        "archive_hash",
        "pom_hash",
        "raw_source_hash",
        "canonical_source_hash",
        "source_tree_hash",
        "scm_revision",
        "selected_path_manifest_hash",
        "correspondence_hash",
        "declaration_fingerprint",
    )
    counts = Counter({item: 0 for item in labels})
    prior = {
        "coordinate": {entry.coordinate for entry in disclosed},
        "family": {
            value for entry in disclosed for value in (entry.coordinate.split(":")[1],)
        },
        "source_url": {entry.source_url for entry in disclosed},
        "archive_hash": {entry.archive_hash for entry in disclosed},
        "pom_hash": {entry.pom_hash for entry in disclosed},
        "raw_source_hash": {
            value for entry in disclosed for value in entry.raw_source_hashes
        },
        "canonical_source_hash": {
            value for entry in disclosed for value in entry.canonical_source_hashes
        },
        "source_tree_hash": {entry.source_tree_hash for entry in disclosed},
        "scm_revision": {entry.scm_revision for entry in disclosed},
        "selected_path_manifest_hash": {
            entry.selected_path_manifest_hash for entry in disclosed
        },
        "correspondence_hash": {entry.correspondence_hash for entry in disclosed},
        "declaration_fingerprint": {
            value for entry in disclosed for value in entry.declaration_fingerprints
        },
    }
    probes = {
        "coordinate": (item["coordinate"],),
        "family": (item["family_id"],),
        "source_url": (item["source_url"],),
        "archive_hash": (item["source_jar_sha256"],),
        "pom_hash": (item["pom_sha256"],),
        "raw_source_hash": item["_raw_source_hashes"],
        "canonical_source_hash": item["_canonical_source_hashes"],
        "source_tree_hash": (item["source_tree_hash"],),
        "scm_revision": (item["immutable_scm_commit"],),
        "selected_path_manifest_hash": (
            (content_hash(tuple(sorted(set(selected_paths)))),)
            if selected_paths
            else ()
        ),
        "correspondence_hash": (
            (item["correspondence"]["correspondence_hash"],)
            if item["correspondence"]
            else ()
        ),
        "declaration_fingerprint": tuple(
            sorted(
                content_hash((item["family_id"], value))
                for value in item["_canonical_source_hashes"]
            )
        ),
    }
    for label, values in probes.items():
        counts[label] = sum(
            value in prior[label] for value in values if value and set(value) != {"0"}
        )
    return counts


def _overlap_report(acquired, selected_manifest):
    disclosed = load_disclosed_java_registry()
    selected_by_family: dict[str, list[str]] = {}
    for row in selected_manifest["files"]:
        selected_by_family.setdefault(row["family_id"], []).append(
            row["source_relative_path"]
        )
    labels = tuple(
        _candidate_overlap_counts(acquired[0], disclosed).keys() if acquired else ()
    )
    counts = Counter({label: 0 for label in labels})
    denied = []
    rows = []
    for item in sorted(acquired, key=lambda value: value["family_id"]):
        candidate_counts = _candidate_overlap_counts(
            item,
            disclosed,
            selected_paths=tuple(selected_by_family.get(item["family_id"], ())),
        )
        overlap_count = sum(candidate_counts.values())
        if overlap_count:
            denied.append(item["family_id"])
        counts.update(candidate_counts)
        row_body = {
            "family_id": item["family_id"],
            "identity_class_overlap_counts": tuple(sorted(candidate_counts.items())),
            "overlap_count": overlap_count,
            "candidate_denied": bool(overlap_count),
        }
        rows.append({**row_body, "row_hash": content_hash(row_body)})
    downloaded = tuple(
        item for item in acquired if item["source_jar_sha256"] != "0" * 64
    )
    body = {
        "schema_version": 1,
        "identity_class_count": len(labels),
        "class_overlap_counts": tuple(sorted(counts.items())),
        "selected_root_overlap_count": sum(counts.values()),
        "denied_candidate_ids": tuple(denied),
        "candidate_rows": tuple(rows),
        "downloaded_candidate_count": len(downloaded),
        "all_downloaded_candidates_appended": True,
        "status": "PASS" if not sum(counts.values()) else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _disclosure_append(acquired, selected_manifest):
    selected_by_family: dict[str, list[str]] = {}
    for row in selected_manifest["files"]:
        selected_by_family.setdefault(row["family_id"], []).append(
            row["source_relative_path"]
        )
    entries = []
    downloaded = tuple(
        item
        for item in sorted(acquired, key=lambda value: value["family_id"])
        if item["source_jar_sha256"] != "0" * 64
    )
    for item in downloaded:
        correspondence_hash = (
            item["correspondence"]["correspondence_hash"]
            if item["correspondence"]
            else "0" * 64
        )
        entry = build_disclosed_java_material_entry(
            coordinate=item["coordinate"],
            version=item["coordinate"].rsplit(":", 1)[-1],
            source_url=item["source_url"],
            archive_hash=item["source_jar_sha256"],
            pom_hash=item["pom_sha256"],
            raw_source_hashes=item["_raw_source_hashes"],
            canonical_source_hashes=item["_canonical_source_hashes"],
            source_tree_hash=item["source_tree_hash"],
            selected_relative_paths=tuple(
                selected_by_family.get(item["family_id"], ())
            ),
            declaration_fingerprints=tuple(
                sorted(
                    content_hash((item["family_id"], value))
                    for value in item["_canonical_source_hashes"]
                )
            ),
            scm_revision=item["immutable_scm_commit"],
            correspondence_hash=correspondence_hash,
            disclosure_reason="DOWNLOADED_DURING_H19",
            originating_chain="E18-R19-F19-H19-E19",
        )
        entries.append(asdict(entry))
    body = {
        "schema_version": 1,
        "downloaded_candidate_count": len(entries),
        "attempted_candidate_count": len(acquired),
        "all_downloaded_candidates_included": len(entries) == len(downloaded),
        "entries": tuple(entries),
    }
    return {**body, "append_hash": content_hash(body)}


def _public_vault_manifest(manifest, content_manifest_hash):
    rows = tuple(
        {
            "candidate_id": item.candidate_id,
            "relative_path": item.relative_canonical_path,
            "role": item.role.value,
            "byte_size": item.byte_size,
            "sha256": item.sha256,
            "parent_artifact_hash": item.parent_artifact_identity,
            "source_use_receipt_hash": item.source_use_receipt_hash,
            "row_hash": item.row_hash,
        }
        for item in manifest.rows
    )
    body = {
        "schema_version": 1,
        "f19_sha": manifest.f19_sha,
        "acquisition_run_id": manifest.acquisition_run_id,
        "file_count": manifest.file_count,
        "tree_hash": manifest.tree_hash,
        "content_manifest_hash": content_manifest_hash,
        "permission_report_hash": manifest.permission_report_hash,
        "write_protection_report_hash": manifest.write_protection_report_hash,
        "seal_timestamp": manifest.seal_timestamp,
        "rows": rows,
        "row_hashes": tuple(item["row_hash"] for item in rows),
    }
    return {**body, "manifest_hash": content_hash(body)}


def _failure_scenarios(candidates, *, locally_excluded=()):
    families = tuple(item["family_id"] for item in candidates)
    organizations = tuple(sorted({item["organization_id"] for item in candidates}))
    rows = []
    scenario_sets = [(f"individual:{family}", {family}) for family in families]
    scenario_sets += [
        (
            f"organization:{organization}",
            {
                item["family_id"]
                for item in candidates
                if item["organization_id"] == organization
            },
        )
        for organization in organizations
    ]
    scenario_sets += [
        (
            f"deterministic-25-offset-{offset}",
            {family for index, family in enumerate(families) if index % 4 == offset},
        )
        for offset in range(4)
    ]
    scenario_sets += [
        (
            f"deterministic-50-seed-{seed_index}",
            set(
                sorted(
                    families,
                    key=lambda family: content_hash(
                        ("m336d-failure-50", seed_index, family)
                    ),
                )[: (len(families) + 1) // 2]
            ),
        )
        for seed_index in range(8)
    ]
    without_sidecars = {
        item["family_id"]
        for item in candidates
        if not item["source_sha256_sidecar_available"]
    }
    organization_counts = Counter(item["organization_id"] for item in candidates)
    largest_count = max(organization_counts.values())
    largest_organizations = {
        organization
        for organization, count in organization_counts.items()
        if count == largest_count
    }
    sizes = sorted(item["source_content_length"] for item in candidates)
    percentile_75 = sizes[max(0, ((3 * len(sizes) + 3) // 4) - 1)]
    multi_license_review = {
        item["family_id"]
        for item in candidates
        if len(item["pom_license_declarations"]) != 1
        or item["pom_license_declarations"][0][0] == "NOASSERTION"
    }
    scenario_sets += [
        ("without-sha256-sidecars", without_sidecars),
        ("scm-only-authenticity", without_sidecars),
        (
            "largest-organization-concentration",
            {
                item["family_id"]
                for item in candidates
                if item["organization_id"] in largest_organizations
            },
        ),
        ("multi-license-review", multi_license_review),
        (
            "above-size-percentile-75",
            {
                item["family_id"]
                for item in candidates
                if item["source_content_length"] >= percentile_75
            },
        ),
        (
            "correlated-apache-hosted-repositories",
            {
                item["family_id"]
                for item in candidates
                if "/apache/" in item["scm_repository"].casefold()
                or item["organization_id"].casefold() == "apache"
            },
        ),
        (
            "correlated-github-metadata-failure",
            {
                item["family_id"]
                for item in candidates
                if urllib.parse.urlsplit(item["scm_repository"]).hostname
                == "github.com"
            },
        ),
        (
            "checksum-endpoint-outage",
            {
                item["family_id"]
                for item in candidates
                if item["source_sha256_sidecar_available"]
            },
        ),
        ("scm-correspondence-failure-after-acquisition", set(families[::3])),
        ("license-review-after-acquisition", multi_license_review),
        ("local-cache-exclusions", set(locally_excluded)),
    ]
    for name, failed in scenario_sets:
        survivors = tuple(family for family in families if family not in failed)
        survivor_orgs = tuple(
            sorted(
                {
                    item["organization_id"]
                    for item in candidates
                    if item["family_id"] in survivors
                }
            )
        )
        body = {
            "scenario_id": name,
            "failed_family_ids": tuple(sorted(failed)),
            "surviving_family_ids": survivors,
            "surviving_organizations": survivor_orgs,
            "surviving_root_count": len(survivors),
        }
        rows.append({**body, "scenario_hash": content_hash(body)})
    minimum_50 = min(
        item["surviving_root_count"] for item in rows if "50" in item["scenario_id"]
    )
    body = {
        "schema_version": 1,
        "scenario_count": len(rows),
        "minimum_roots_surviving_50_percent_loss": minimum_50,
        "preferred_five_roots_survive": minimum_50 >= 5,
        "scenarios": tuple(rows),
    }
    return {**body, "report_hash": content_hash(body)}


def _sidecar_value(raw: bytes) -> str:
    try:
        fields = raw.decode("ascii", errors="strict").strip().casefold().split()
    except UnicodeDecodeError as exc:
        raise ValueError("metadata SHA-256 sidecar is not ASCII") from exc
    if not fields or not _HASH.fullmatch(fields[0]) or len(fields) > 2:
        raise ValueError("metadata SHA-256 sidecar is malformed")
    return fields[0]


def _pom_declared_java_releases(raw: bytes) -> tuple[tuple[str, str], ...]:
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Maven POM DTD and external entities are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("malformed Maven POM XML") from exc
    names = {
        "java.version",
        "jdk.version",
        "maven.compiler.release",
        "maven.compiler.source",
        "maven.compiler.target",
    }
    rows = set()
    for node in root.iter():
        name = node.tag.rsplit("}", 1)[-1]
        value = (node.text or "").strip()
        if name in names and value:
            rows.add((name, value))
    return tuple(sorted(rows))


def _pom_packaging(raw: bytes) -> str:
    """Return declared Maven packaging; Maven defaults an omission to ``jar``."""

    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Maven POM DTD and external entities are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("malformed Maven POM XML") from exc
    values = tuple(
        (node.text or "").strip()
        for node in root
        if node.tag.rsplit("}", 1)[-1] == "packaging" and (node.text or "").strip()
    )
    if len(values) > 1:
        raise ValueError("Maven POM contains duplicate packaging metadata")
    return values[0] if values else "jar"


def _performance_summary(samples: list[float]) -> dict:
    ordered = sorted(samples)

    def percentile(value: float) -> str:
        index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * value + 0.5)))
        return f"{ordered[index]:.9f}"

    return {
        "sample_count": len(ordered),
        "p50_seconds": percentile(0.50),
        "p95_seconds": percentile(0.95),
        "p99_seconds": percentile(0.99),
        "total_seconds": f"{sum(ordered):.9f}",
    }


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _zip_root_prefix(archive: zipfile.ZipFile) -> str:
    roots = {
        PurePosixPath(item.filename).parts[0]
        for item in archive.infolist()
        if item.filename
    }
    if len(roots) != 1:
        raise ValueError("SCM archive root is ambiguous")
    return next(iter(roots)) + "/"


def _set_read_only(root: Path) -> None:
    for path in (item for item in root.rglob("*") if item.is_file()):
        path.chmod(
            stat.S_IMODE(path.stat().st_mode)
            & ~stat.S_IWUSR
            & ~stat.S_IWGRP
            & ~stat.S_IWOTH
        )


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
