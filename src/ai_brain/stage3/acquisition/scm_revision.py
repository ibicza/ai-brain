"""Independent Git ref and commit-addressed source-tree verification."""

from __future__ import annotations

import io
import re
import subprocess
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    ScmRevisionVerificationReceipt,
    verify_scm_revision_receipt,
)

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_GITHUB = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?\Z"
)
_LICENSE_NAMES = frozenset({"license", "license.txt", "license.md"})
MAX_SCM_ARCHIVE_ENTRIES = 100_000
MAX_SCM_ARCHIVE_BYTES = 768 * 1024 * 1024


@dataclass(frozen=True)
class VerifiedScmRevision:
    receipt: ScmRevisionVerificationReceipt
    java_entries: tuple[tuple[str, bytes], ...]
    license_entries: tuple[tuple[str, bytes], ...]
    archive_payload: bytes


class ScmRevisionProvider:
    """Verify a frozen Git tag through Git transport and commit-addressed HTTPS."""

    def __init__(self, *, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds

    def verify(
        self,
        *,
        repository_url: str,
        requested_ref: str,
    ) -> VerifiedScmRevision:
        canonical, owner, repository = canonical_github_repository(repository_url)
        if not requested_ref.startswith("refs/tags/"):
            raise ValueError("SCM verification requires an exact frozen tag ref")
        command = (
            "git",
            "ls-remote",
            canonical,
            requested_ref,
            f"{requested_ref}^{{}}",
        )
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=self.timeout_seconds,
        )
        response = result.stdout
        rows = _parse_ls_remote(response, requested_ref)
        direct = rows.get(requested_ref)
        peeled = rows.get(f"{requested_ref}^{{}}")
        if direct is None:
            raise ValueError("frozen SCM ref was not resolved")
        immutable_commit = peeled or direct
        tag_object = direct if peeled is not None else None
        archive_url = (
            f"https://github.com/{owner}/{repository}/archive/{immutable_commit}.zip"
        )
        request_body = {
            "repository_url": canonical,
            "requested_ref": requested_ref,
            "resolved_commit": immutable_commit,
            "archive_url": archive_url,
        }
        request = urllib.request.Request(
            archive_url, headers={"User-Agent": "ai-brain-scm-provenance/2"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as opened:
            final_url = opened.geturl()
            payload = opened.read()
        final = urllib.parse.urlsplit(final_url)
        if (
            final.scheme != "https"
            or final.hostname != "codeload.github.com"
            or immutable_commit not in final.path
        ):
            raise ValueError("commit-addressed SCM archive left the frozen identity")
        java_entries, licenses, tree_hash = _inspect_github_archive(payload)
        license = licenses[0] if licenses else None
        response_body = {
            "final_url": final_url,
            "archive_sha256": bytes_hash(payload),
            "archive_size": len(payload),
            "source_tree_hash": tree_hash,
        }
        receipt_body = {
            "repository_url": canonical,
            "requested_ref": requested_ref,
            "immutable_commit": immutable_commit,
            "tag_to_commit_verified": True,
            "source_tree_hash": tree_hash,
            "tag_object": tag_object,
            "remote_ref_response_hash": bytes_hash(response),
            "commit_retrieval_request_hash": content_hash(request_body),
            "commit_retrieval_response_hash": content_hash(response_body),
            "source_archive_sha256": bytes_hash(payload),
            "license_path": license[0] if license else None,
            "license_raw_sha256": bytes_hash(license[1]) if license else None,
        }
        receipt = ScmRevisionVerificationReceipt(
            **receipt_body, receipt_hash=content_hash(receipt_body)
        )
        verify_scm_revision_receipt(receipt)
        return VerifiedScmRevision(receipt, java_entries, licenses, payload)


def canonical_github_repository(value: str) -> tuple[str, str, str]:
    normalized = value.strip().replace("git://github.com/", "https://github.com/")
    if normalized.startswith("scm:git:"):
        normalized = normalized.removeprefix("scm:git:")
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix("git@github.com:")
    match = _GITHUB.fullmatch(normalized.rstrip("/"))
    if match is None:
        raise ValueError("SCM repository is not a canonical GitHub Git identity")
    owner = match.group("owner")
    repository = match.group("repo")
    return f"https://github.com/{owner}/{repository}.git", owner, repository


def _parse_ls_remote(raw: bytes, requested_ref: str) -> dict[str, str]:
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("SCM ref response is not ASCII") from exc
    result = {}
    allowed = {requested_ref, f"{requested_ref}^{{}}"}
    for line in text.splitlines():
        fields = line.split("\t")
        if (
            len(fields) != 2
            or fields[1] not in allowed
            or not _COMMIT.fullmatch(fields[0])
        ):
            raise ValueError("SCM ref response contains an unexpected row")
        if fields[1] in result:
            raise ValueError("SCM ref response contains a duplicate row")
        result[fields[1]] = fields[0]
    return result


def _inspect_github_archive(
    raw: bytes,
) -> tuple[tuple[tuple[str, bytes], ...], tuple[tuple[str, bytes], ...], str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("malformed commit-addressed SCM archive") from exc
    infos = archive.infolist()
    if not infos or len(infos) > MAX_SCM_ARCHIVE_ENTRIES:
        raise ValueError("SCM archive entry denominator is invalid")
    java_entries = []
    licenses = []
    rows = []
    total = 0
    seen = set()
    for info in infos:
        if info.is_dir():
            continue
        parts = PurePosixPath(info.filename).parts
        if len(parts) < 2 or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("SCM archive contains an unsafe path")
        relative = PurePosixPath(*parts[1:]).as_posix()
        if relative in seen:
            raise ValueError("SCM archive contains a duplicate path")
        seen.add(relative)
        total += info.file_size
        if total > MAX_SCM_ARCHIVE_BYTES:
            raise ValueError("SCM archive uncompressed size limit exceeded")
        payload = archive.read(info)
        rows.append((relative, bytes_hash(payload), len(payload)))
        if relative.endswith(".java"):
            java_entries.append((relative, payload))
        if (
            len(PurePosixPath(relative).parts) == 1
            and PurePosixPath(relative).name.casefold() in _LICENSE_NAMES
        ):
            licenses.append((relative, payload))
    archive.close()
    return (
        tuple(sorted(java_entries)),
        tuple(sorted(licenses)),
        content_hash(tuple(sorted(rows))),
    )
