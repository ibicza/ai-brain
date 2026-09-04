"""Capture the allowed metadata-only M-33.6b final-candidate observations."""

from __future__ import annotations

import argparse
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336b_provenance import frozen_m336b_candidate_pool


def _http(method: str, url: str):
    request = urllib.request.Request(
        url, method=method, headers={"User-Agent": "ai-brain-m336b-metadata/1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read() if method == "GET" else b""
            return {
                "method": method,
                "requested_url": url,
                "response_url": response.geturl(),
                "status": response.status,
                "content_length": response.headers.get("Content-Length"),
                "response_body_byte_count": len(payload),
                "response_body_sha256": bytes_hash(payload) if payload else None,
            }, payload
    except urllib.error.HTTPError as exc:
        return {
            "method": method,
            "requested_url": url,
            "response_url": exc.geturl(),
            "status": exc.code,
            "content_length": exc.headers.get("Content-Length"),
            "response_body_byte_count": 0,
            "response_body_sha256": None,
        }, b""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("metadata audit output must be new")
    events = []
    scm = []
    for candidate in frozen_m336b_candidate_pool():
        base = (
            f"{candidate.coordinate.repository}/"
            f"{candidate.coordinate.canonical_repository_path}"
        )
        pom_url = base.removesuffix("-sources.jar") + ".pom"
        pom_event, pom = _http("GET", pom_url)
        if bytes_hash(pom) != candidate.metadata_pom_sha256:
            raise ValueError("candidate POM changed after metadata freeze")
        events.append(pom_event)
        source_event, _ = _http("HEAD", base)
        if int(source_event["content_length"] or -1) != candidate.source_content_length:
            raise ValueError("candidate source length changed after metadata freeze")
        events.append(source_event)
        for suffix in (".sha256", ".asc"):
            event, _ = _http("HEAD", base + suffix)
            events.append(event)
        process = subprocess.run(
            (
                "git",
                "ls-remote",
                candidate.expected_scm_repository,
                candidate.requested_scm_ref,
                candidate.requested_scm_ref + "^{}",
            ),
            check=True,
            capture_output=True,
        )
        scm.append(
            {
                "repository": candidate.expected_scm_repository,
                "requested_ref": candidate.requested_scm_ref,
                "request_hash": content_hash(
                    (candidate.expected_scm_repository, candidate.requested_scm_ref)
                ),
                "response_sha256": bytes_hash(process.stdout),
                "response_line_count": len(process.stdout.splitlines()),
            }
        )
    body = {
        "schema_version": 1,
        "candidate_count": len(frozen_m336b_candidate_pool()),
        "http_events": tuple(events),
        "scm_metadata_events": tuple(scm),
        "pom_get_count": sum(
            item["method"] == "GET" and item["requested_url"].endswith(".pom")
            for item in events
        ),
        "source_head_count": sum(
            item["method"] == "HEAD" and item["requested_url"].endswith("-sources.jar")
            for item in events
        ),
        "fresh_source_jar_get_count": sum(
            item["method"] == "GET" and item["requested_url"].endswith("-sources.jar")
            for item in events
        ),
        "fresh_source_tree_body_get_count": 0,
        "fresh_java_body_inspection_count": 0,
        "source_body_response_byte_count": sum(
            item["response_body_byte_count"]
            for item in events
            if item["requested_url"].endswith(("-sources.jar", ".zip", ".tar.gz"))
        ),
    }
    report = {**body, "report_hash": content_hash(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    if (
        body["pom_get_count"] != body["candidate_count"]
        or body["source_head_count"] != body["candidate_count"]
        or body["fresh_source_jar_get_count"]
        or body["fresh_source_tree_body_get_count"]
        or body["fresh_java_body_inspection_count"]
        or body["source_body_response_byte_count"]
    ):
        raise SystemExit("metadata-only boundary was violated")


if __name__ == "__main__":
    main()
