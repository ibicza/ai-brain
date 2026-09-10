"""Discover a fresh M336K2 pool using metadata, HEAD, and ref queries only.

The script never performs a GET for a source JAR or SCM archive.  POM, Maven
search, digest sidecars, and Git ref advertisements are treated as metadata.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_acquisition import (
    validate_m336k2_candidate_pool,
)

_MAVEN = "https://repo.maven.apache.org/maven2"
_BROWSE = "https://central.sonatype.com/api/internal/browse/components"
_USER_AGENT = "ai-brain-m336k2-metadata-only/1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument(
        "--exclusion-file",
        type=Path,
        action="append",
        default=[],
        help="additional prior-pool, registry, cache, or vault metadata receipt",
    )
    parser.add_argument("--target-count", type=int, default=96)
    parser.add_argument("--maximum-search-pages", type=int, default=25)
    parser.add_argument("--metadata-workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K2 metadata pool output must be fresh")
    if args.target_count < 80:
        raise ValueError("M336K2 metadata pool target must be at least 80")
    repository = args.repository.resolve(strict=True)
    git = args.git_executable.resolve(strict=True)
    excluded = _collect_exclusions(repository, git, args.exclusion_file)
    candidates = []
    organizations: Counter[str] = Counter()
    seen_coordinates = set(excluded["coordinate"])
    for page in range(args.maximum_search_pages):
        docs = _search_page(page)
        batch_size = max(args.metadata_workers, 1)
        for offset in range(0, len(docs), batch_size):
            batch = docs[offset : offset + batch_size]
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=args.metadata_workers
            ) as executor:
                discovered = tuple(
                    executor.map(lambda doc: _candidate_from_metadata(doc, git), batch)
                )
            for candidate in discovered:
                if candidate is None:
                    continue
                if any(
                    candidate.get(field) in excluded[field]
                    for field in excluded
                    if candidate.get(field)
                ):
                    continue
                coordinate = candidate["coordinate"]
                organization = candidate["organization_id"]
                if coordinate in seen_coordinates or organizations[organization] >= 2:
                    continue
                candidates.append(candidate)
                seen_coordinates.add(coordinate)
                organizations[organization] += 1
                if len(candidates) >= args.target_count:
                    break
            if len(candidates) >= args.target_count:
                break
        if len(candidates) >= args.target_count:
            break
    candidates.sort(key=lambda item: item["family_id"].encode("utf-8"))
    organizations = Counter(item["organization_id"] for item in candidates)
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_METADATA_ONLY_CANDIDATE_POOL",
        "candidate_count": len(candidates),
        "organization_count": len(organizations),
        "maximum_candidates_per_organization": max(organizations.values(), default=0),
        "pre_freeze_source_body_bytes": 0,
        "claims_final_eligibility": False,
        "metadata_request_count": _request_counters["metadata"],
        "source_body_get_count": 0,
        "scm_archive_body_get_count": 0,
        "java_source_body_read_count": 0,
        "excluded_identity_counts": {
            key: len(value) for key, value in sorted(excluded.items())
        },
        "candidates": candidates,
    }
    pool = {**body, "pool_hash": content_hash(body)}
    validate_m336k2_candidate_pool(pool)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(pool) + "\n", encoding="utf-8", newline="\n")
    print(
        canonical_json(
            {
                "candidate_count": len(candidates),
                "organization_count": len(organizations),
                "maximum_candidates_per_organization": max(
                    organizations.values(), default=0
                ),
                "pool_hash": pool["pool_hash"],
                "source_body_get_count": 0,
                "scm_archive_body_get_count": 0,
                "status": "PASS",
            }
        )
    )


_request_counters = Counter()


def _search_page(page: int) -> tuple[dict, ...]:
    value = _metadata_json_post(
        _BROWSE,
        {
            "page": page,
            "size": 20,
            "searchTerm": "",
            "sortField": "publishedDate",
            "sortDirection": "desc",
            "filter": [],
        },
    )
    documents = []
    for component in value.get("components", ()):
        latest = component.get("latestVersionInfo") or {}
        documents.append(
            {
                "g": component.get("namespace"),
                "a": component.get("name"),
                "v": latest.get("version"),
                "p": component.get("packaging"),
                "ec": component.get("ec") or (),
                "timestamp": latest.get("timestampUnixWithMS"),
            }
        )
    return tuple(documents)


def _candidate_from_metadata(doc: dict, git: Path) -> dict | None:
    group = doc.get("g")
    artifact = doc.get("a")
    version = doc.get("v")
    if (
        not all(isinstance(item, str) and item for item in (group, artifact, version))
        or version.endswith("-SNAPSHOT")
        or doc.get("p") not in {None, "jar"}
    ):
        return None
    stem = "/".join(group.split(".")) + f"/{artifact}/{version}/{artifact}-{version}"
    pom_url = f"{_MAVEN}/{stem}.pom"
    source_url = f"{_MAVEN}/{stem}-sources.jar"
    try:
        source_head = _head(source_url)
        length = int(source_head.get("content-length", "0"))
        if length <= 0:
            return None
        pom_raw = _metadata_bytes(pom_url, maximum=2_000_000)
        pom = _pom_metadata(pom_raw)
        repository = _normalize_scm(pom["scm"])
        if repository is None:
            return None
        tag, commit = _resolve_tag(git, repository, pom["tag"], version)
        if tag is None or commit is None:
            return None
        owner = (
            urllib.parse.urlsplit(repository).path.strip("/").split("/")[0].casefold()
        )
        if not owner:
            return None
        source_digest = None
        signature = False
        scm_archive = _github_archive(repository, commit)
        scm_head = _head_optional(scm_archive)
        if scm_head is None:
            return None
        family = _slug(f"{owner}-{artifact}-{version}")
        dependency_count = len(pom["dependencies"])
        authority_hashes = (
            content_hash(tuple(sorted(source_head.items()))),
            content_hash(tuple(sorted(scm_head.items()))),
            hashlib.sha256(pom_raw).hexdigest(),
            content_hash((repository, tag, commit)),
        )
        body = {
            "family_id": family,
            "organization_id": owner,
            "group_id": group,
            "artifact_id": artifact,
            "version": version,
            "coordinate": f"{group}:{artifact}:{version}",
            "packaging": "jar",
            "source_url": source_url,
            "pom_url": pom_url,
            "scm_repository": repository,
            "scm_ref": f"refs/tags/{tag}",
            "scm_commit": commit,
            "scm_archive_head_url": scm_archive,
            "source_content_length": length,
            "source_etag": source_head.get("etag"),
            "source_last_modified": source_head.get("last-modified"),
            "source_sha256_sidecar_available": bool(
                source_digest and len(source_digest) == 64
            ),
            "source_sha256_sidecar_value": (
                source_digest if source_digest and len(source_digest) == 64 else None
            ),
            "source_sha1_sidecar_value": (
                source_digest if source_digest and len(source_digest) == 40 else None
            ),
            "source_signature_available": signature,
            "metadata_pom_sha256": hashlib.sha256(pom_raw).hexdigest(),
            "pom_scm_metadata": (pom["scm"], pom["url"], pom["tag"]),
            "pom_license_declarations": pom["licenses"],
            "metadata_receipt_hashes": tuple(sorted(authority_hashes)),
            "repository_source_prefixes": (),
            "compile_dependency_metadata": pom["dependencies"],
            "unresolved_external_compile_dependency_count": dependency_count,
            "metadata_compilation_risk": (
                "ZERO_EXTERNAL_COMPILE_DEPENDENCIES"
                if dependency_count == 0
                else "UNRESOLVED_EXTERNAL_COMPILE_DEPENDENCIES"
            ),
            "metadata_authority": {
                "maven_search_timestamp": doc.get("timestamp"),
                "source_head_receipt_hash": content_hash(
                    tuple(sorted(source_head.items()))
                ),
                "scm_head_receipt_hash": content_hash(tuple(sorted(scm_head.items()))),
                "pom_bytes_hash": hashlib.sha256(pom_raw).hexdigest(),
                "git_ref_advertisement": True,
                "source_body_observed": False,
                "scm_archive_body_observed": False,
            },
            "requirement": "OPTIONAL",
        }
        return {**body, "policy_hash": content_hash(body)}
    except (
        OSError,
        ValueError,
        ET.ParseError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return None


def _pom_metadata(raw: bytes) -> dict:
    root = ET.fromstring(raw)

    scm = root.find("{*}scm")
    connection = ""
    url = ""
    tag = ""
    if scm is not None:
        for child in scm:
            name = child.tag.rsplit("}", 1)[-1]
            value = (child.text or "").strip()
            if name in {"connection", "developerConnection"} and not connection:
                connection = value
            elif name == "url":
                url = value
            elif name == "tag":
                tag = value
    licenses = []
    for item in root.findall(".//{*}licenses/{*}license"):
        name = _child_text(item, "name")
        license_url = _child_text(item, "url")
        if name or license_url:
            licenses.append(
                (
                    _metadata_spdx_identifier(name, license_url),
                    license_url,
                    content_hash((name, license_url)),
                )
            )
    dependencies = []
    for item in root.findall(".//{*}dependencies/{*}dependency"):
        scope = _child_text(item, "scope") or "compile"
        optional = _child_text(item, "optional").casefold() == "true"
        if scope in {"compile", "provided"} and not optional:
            dependencies.append(
                (
                    _child_text(item, "groupId"),
                    _child_text(item, "artifactId"),
                    _child_text(item, "version"),
                    scope,
                )
            )
    return {
        "scm": connection or url,
        "url": url,
        "tag": tag,
        "licenses": tuple(sorted(set(licenses))),
        "dependencies": tuple(sorted(set(dependencies))),
    }


def _child_text(node: ET.Element, name: str) -> str:
    child = node.find(f"{{*}}{name}")
    return "" if child is None or child.text is None else child.text.strip()


def _metadata_spdx_identifier(name: str, url: str) -> str:
    value = f"{name} {url}".casefold()
    rules = (
        (("apache", "2.0"), "Apache-2.0"),
        (("mit",), "MIT"),
        (("eclipse public license", "2.0"), "EPL-2.0"),
        (("eclipse public license", "1.0"), "EPL-1.0"),
        (("mozilla public license", "2.0"), "MPL-2.0"),
        (("bsd", "3"), "BSD-3-Clause"),
        (("bsd", "2"), "BSD-2-Clause"),
        (("isc",), "ISC"),
        (("unlicense",), "Unlicense"),
        (("lgpl", "2.1"), "LGPL-2.1-only"),
        (("lgpl", "3"), "LGPL-3.0-only"),
        (("gpl", "2"), "GPL-2.0-only"),
        (("gpl", "3"), "GPL-3.0-only"),
    )
    for tokens, identifier in rules:
        if all(token in value for token in tokens):
            return identifier
    return "NOASSERTION"


def _normalize_scm(value: str) -> str | None:
    value = value.strip()
    for prefix in ("scm:git:", "scm:git:git:"):
        value = value.removeprefix(prefix)
    value = value.replace("git@github.com:", "https://github.com/")
    value = value.replace("git://github.com/", "https://github.com/")
    value = value.replace("http://github.com/", "https://github.com/")
    if not value.startswith("https://github.com/"):
        return None
    parsed = urllib.parse.urlsplit(value)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) != 2:
        return None
    return f"https://github.com/{parts[0]}/{parts[1]}.git"


def _resolve_tag(
    git: Path, repository: str, declared: str, version: str
) -> tuple[str | None, str | None]:
    tags = []
    if declared and declared.casefold() not in {"head", "master", "main"}:
        tags.append(declared.removeprefix("refs/tags/"))
    tags.extend((version, f"v{version}", f"release-{version}"))
    result = subprocess.run(
        (str(git), "ls-remote", "--tags", repository),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=12,
    )
    rows = [line.split() for line in result.stdout.splitlines() if line.split()]
    for tag in dict.fromkeys(tags):
        exact = [row for row in rows if row[1] == f"refs/tags/{tag}"]
        peeled = [row for row in rows if row[1] == f"refs/tags/{tag}^{{}}"]
        selected = peeled[-1] if peeled else (exact[-1] if exact else None)
        if selected and re.fullmatch(r"[0-9a-f]{40}", selected[0]):
            return tag, selected[0]
    return None, None


def _github_archive(repository: str, commit: str) -> str:
    parts = urllib.parse.urlsplit(repository).path.strip("/").removesuffix(".git")
    return f"https://codeload.github.com/{parts}/zip/{commit}"


def _digest_sidecar(url: str) -> str | None:
    for suffix, length in ((".sha256", 64), (".sha1", 40)):
        try:
            raw = _metadata_bytes(url + suffix, maximum=512).decode("ascii").strip()
        except (OSError, UnicodeDecodeError):
            continue
        token = raw.split()[0] if raw else ""
        if len(token) == length and all(
            char in "0123456789abcdefABCDEF" for char in token
        ):
            return token.casefold()
    return None


def _head_optional(url: str) -> dict[str, str] | None:
    try:
        return _head(url)
    except OSError:
        return None


def _head(url: str) -> dict[str, str]:
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": _USER_AGENT}
    )
    _request_counters["metadata"] += 1
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise OSError(f"metadata HEAD failed: {response.status}")
        return {key.casefold(): value for key, value in response.headers.items()}


def _metadata_json(url: str) -> dict:
    return json.loads(_metadata_bytes(url, maximum=10_000_000))


def _metadata_json_post(url: str, payload: dict) -> dict:
    encoded = canonical_json(payload).encode("utf-8")
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            data=encoded,
            method="POST",
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        _request_counters["metadata"] += 1
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ValueError("metadata response exceeds bound")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise TypeError("metadata response is not an object")
            return value
        except (OSError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise AssertionError("unreachable metadata POST retry state")


def _metadata_bytes(url: str, *, maximum: int) -> bytes:
    lowered = urllib.parse.urlsplit(url).path.casefold()
    if lowered.endswith(("-sources.jar", ".zip", ".tar", ".tar.gz", ".tgz")):
        raise ValueError("source/archive body GET is forbidden before F28")
    raw = None
    for attempt in range(3):
        request = urllib.request.Request(
            url, method="GET", headers={"User-Agent": _USER_AGENT}
        )
        _request_counters["metadata"] += 1
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read(maximum + 1)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    assert raw is not None
    if len(raw) > maximum:
        raise ValueError("metadata response exceeds bound")
    return raw


def _collect_exclusions(
    repository: Path, git: Path, additional_files: list[Path]
) -> dict[str, set[str]]:
    fields = (
        "family_id",
        "coordinate",
        "source_url",
        "scm_repository",
        "scm_ref",
        "scm_commit",
        "metadata_pom_sha256",
        "source_sha256_sidecar_value",
    )
    values = {field: set() for field in fields}
    paths = set(repository.rglob("candidate_pool.json"))
    paths.update(path.resolve(strict=True) for path in additional_files)
    registry = repository / "artifacts" / "acquisition" / "disclosed_java"
    if registry.is_dir():
        paths.update(registry.rglob("*.json"))
        paths.update(registry.rglob("*.jsonl"))
    for path in paths:
        try:
            if path.suffix == ".jsonl":
                documents = [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line
                ]
            else:
                documents = [json.loads(path.read_text(encoding="utf-8"))]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for document in documents:
            _collect_fields(document, values)
    history = subprocess.run(
        (str(git), "rev-list", "--objects", "--all"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    ).stdout.splitlines()
    for row in history:
        object_id, separator, name = row.partition(" ")
        if (
            not separator
            or not name.casefold().endswith("candidate_pool.json")
            or not re.fullmatch(r"[0-9a-f]{40,64}", object_id)
        ):
            continue
        raw = subprocess.run(
            (str(git), "cat-file", "blob", object_id),
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
        try:
            _collect_fields(json.loads(raw), values)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return values


def _collect_fields(value, fields: dict[str, set[str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in fields and isinstance(item, str) and item:
                fields[key].add(item)
            _collect_fields(item, fields)
    elif isinstance(value, list):
        for item in value:
            _collect_fields(item, fields)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120]


if __name__ == "__main__":
    main()
