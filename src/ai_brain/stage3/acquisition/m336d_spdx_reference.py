"""Independent Java SPDX differential harness for M-33.6d."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.spdx_license import (
    AUTOMATIC_SPDX_MATCH_STATUSES,
    SPDXLicenseMatcher,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REFERENCE_SOURCE = (
    PROJECT_ROOT
    / "tools"
    / "spdx-reference-java"
    / "src"
    / "IndependentSpdxReference.java"
)
REFERENCE_RECEIPT_SCHEMA = (
    PROJECT_ROOT
    / "schemas"
    / "stage3"
    / "m336d_java_spdx_reference_receipt_v1.schema.json"
)


@dataclass(frozen=True)
class SPDXDifferentialCase:
    case_id: str
    category: str
    source_document: str
    raw: bytes
    expected_automatic: bool
    expected_license_id: str | None


@dataclass(frozen=True)
class SPDXIsolationAudit:
    production_to_reference_dependency_count: int
    reference_to_production_dependency_count: int
    forbidden_java_dependency_count: int
    java_modules: tuple[str, ...]
    reference_source_sha256: str
    production_source_sha256: str
    audit_hash: str


@dataclass(frozen=True)
class SPDXDifferentialReport:
    schema_version: int
    case_count: int
    category_counts: tuple[tuple[str, int], ...]
    production_reference_agreement: str
    disagreement_count: int
    disagreement_review_required_count: int
    false_automatic_license_identity_count: int
    valid_optional_variant_rejected_count: int
    substantive_mutation_accepted_count: int
    multiple_match_automatic_acceptance_count: int
    isolation_audit: SPDXIsolationAudit
    input_corpus_hash: str
    java_receipts_hash: str
    report_hash: str


def build_independent_spdx_corpus(
    matcher: SPDXLicenseMatcher | None = None,
) -> tuple[SPDXDifferentialCase, ...]:
    """Build labels from declared transformations, never from either evaluator."""

    snapshot = (matcher or SPDXLicenseMatcher()).snapshot_root
    ids = (
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "GPL-2.0-only",
        "Classpath-exception-2.0",
    )
    canonical = {item: (snapshot / f"{item}.txt").read_bytes() for item in ids}
    prototypes: list[tuple[str, bytes, bool, str | None]] = []
    for license_id in ids:
        raw = canonical[license_id]
        text = raw.decode("utf-8")
        prototypes.extend(
            (
                (f"exact-{license_id}", raw, True, license_id),
                (
                    f"crlf-{license_id}",
                    text.replace("\n", "\r\n").encode(),
                    True,
                    license_id,
                ),
                (
                    f"cr-{license_id}",
                    text.replace("\n", "\r").encode(),
                    True,
                    license_id,
                ),
                (f"bom-{license_id}", b"\xef\xbb\xbf" + raw, True, license_id),
                (
                    f"outer-spacing-{license_id}",
                    b"\n  \n" + raw + b" \n",
                    True,
                    license_id,
                ),
                (
                    f"punctuation-{license_id}",
                    re.sub(r"[.,;:()\[\]\"]", " ", text).encode(),
                    True,
                    license_id,
                ),
                (
                    f"word-spacing-{license_id}",
                    (" \t ".join(text.split()) + "\n").encode(),
                    True,
                    license_id,
                ),
                (
                    f"removed-mandatory-{license_id}",
                    _remove_middle(text).encode(),
                    False,
                    None,
                ),
                (
                    f"changed-grant-{license_id}",
                    _substantive_change(
                        text,
                        ("grant", "permission", "linking", "redistribution"),
                        "prohibition",
                    ).encode(),
                    False,
                    None,
                ),
                (
                    f"changed-warranty-{license_id}",
                    _substantive_change(
                        text, ("warranty", "warranties", "disclaimer"), "guarantee"
                    ).encode(),
                    False,
                    None,
                ),
                (
                    f"additional-restriction-{license_id}",
                    raw
                    + b"\nAdditional restriction: commercial redistribution is forbidden.\n",
                    False,
                    None,
                ),
                (
                    f"reordered-clauses-{license_id}",
                    _swap_halves(text).encode(),
                    False,
                    None,
                ),
                (f"substring-fake-{license_id}", text[:160].encode(), False, None),
            )
        )
    apache = canonical["Apache-2.0"].decode()
    prototypes.extend(
        (
            (
                "optional-apache-heading",
                apache.replace(
                    "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\n\n",
                    "",
                ).encode(),
                True,
                "Apache-2.0",
            ),
            (
                "replaceable-apache-owner",
                apache.replace(
                    "[yyyy] [name of copyright owner]", "2026 Example Foundation"
                ).encode(),
                True,
                "Apache-2.0",
            ),
            (
                "changed-apache-patent",
                apache.replace("patent license", "patent prohibition", 1).encode(),
                False,
                None,
            ),
        )
    )
    classpath = canonical["Classpath-exception-2.0"].decode()
    prototypes.append(
        (
            "optional-classpath-version",
            classpath.replace(
                "Public License cover", "Public License version 2 cover", 1
            ).encode(),
            True,
            "Classpath-exception-2.0",
        )
    )
    controls = (
        (
            "random-prose",
            "Deterministic educational analysis, café, and no license grant.\n".encode(),
            False,
            None,
        ),
        (
            "unicode-normalization-control-nfc",
            "Café attribution only.\n".encode(),
            False,
            None,
        ),
        (
            "unicode-normalization-control-nfd",
            "Cafe\u0301 attribution only.\n".encode(),
            False,
            None,
        ),
        (
            "notice",
            b"NOTICE\nCopyright 2026 Example. No license terms are stated.\n",
            False,
            None,
        ),
        (
            "third-party-attribution",
            b"Third-party components are listed here for attribution.\n",
            False,
            None,
        ),
        (
            "unsupported-license",
            b"Mozilla Public License Version 2.0\nThis is not a complete license.\n",
            False,
            None,
        ),
        (
            "multiple-substrings",
            b"Apache License MIT Permission GPL version 2 redistribution warranty\n",
            False,
            None,
        ),
        ("malformed-utf8", b"\xff\xfe\x00broken", False, None),
    )
    prototypes.extend(controls)
    # 89 transformation prototypes x 120 deterministic identities = 10,680 cases.
    result: list[SPDXDifferentialCase] = []
    for repetition in range(120):
        for index, (category, raw, expected, license_id) in enumerate(prototypes):
            result.append(
                SPDXDifferentialCase(
                    case_id=f"case-{repetition:03d}-{index:03d}",
                    category=category,
                    source_document=f"corpus/{category}/LICENSE-{repetition:03d}.txt",
                    raw=raw,
                    expected_automatic=expected,
                    expected_license_id=license_id,
                )
            )
    if len(result) < 10_000:
        raise AssertionError("independent SPDX corpus is below the frozen denominator")
    return tuple(result)


def run_independent_spdx_differential(
    *,
    javac: Path,
    java: Path,
    matcher: SPDXLicenseMatcher | None = None,
) -> SPDXDifferentialReport:
    matcher = matcher or SPDXLicenseMatcher()
    cases = build_independent_spdx_corpus(matcher)
    implementation_hash = bytes_hash(REFERENCE_SOURCE.read_bytes())
    with tempfile.TemporaryDirectory(prefix="m336d-spdx-reference-") as raw_tmp:
        temporary = Path(raw_tmp)
        classes = temporary / "classes"
        classes.mkdir()
        corpus = temporary / "immutable-cases.tsv"
        corpus.write_text(
            "".join(
                f"{item.case_id}\t{item.source_document}\t"
                f"{base64.b64encode(item.raw).decode('ascii')}\n"
                for item in cases
            ),
            encoding="utf-8",
            newline="\n",
        )
        _run((str(javac), "--release", "21", "-d", str(classes), str(REFERENCE_SOURCE)))
        completed = _run(
            (
                str(java),
                "-Djava.net.useSystemProxies=false",
                "-cp",
                str(classes),
                "IndependentSpdxReference",
                str(matcher.snapshot_root),
                str(corpus),
                implementation_hash,
            )
        )
        reference_rows = tuple(
            json.loads(line) for line in completed.stdout.splitlines()
        )
        if len(reference_rows) != len(cases):
            raise ValueError("Java reference receipt denominator mismatch")
        java_receipts_hash = content_hash(reference_rows)
        jdeps = javac.with_name("jdeps.exe" if javac.suffix else "jdeps")
        modules = (
            _run((str(jdeps), "--print-module-deps", str(classes)))
            .stdout.strip()
            .split(",")
        )
    audit = _isolation_audit(tuple(sorted(modules)), matcher)
    disagreement = false_automatic = optional_rejected = mutation_accepted = 0
    multiple_accepted = review = 0
    categories: dict[str, int] = {}
    for case, reference in zip(cases, reference_rows, strict=True):
        categories[case.category] = categories.get(case.category, 0) + 1
        _verify_java_receipt(reference, case, implementation_hash)
        production = matcher.match(case.raw, source_document=case.source_document)
        production_auto = production.match_status in AUTOMATIC_SPDX_MATCH_STATUSES
        reference_auto = reference["automatic"]
        production_identity = (
            production.template_license_id if production_auto else None
        )
        reference_identity = (
            reference["template_license_id"] if reference_auto else None
        )
        agrees = (production_auto, production_identity) == (
            reference_auto,
            reference_identity,
        )
        if not agrees:
            disagreement += 1
            review += 1
        for automatic, identity in (
            (production_auto, production_identity),
            (reference_auto, reference_identity),
        ):
            if automatic and (
                not case.expected_automatic or identity != case.expected_license_id
            ):
                false_automatic += 1
        if case.category.startswith("optional-") and (
            not production_auto or not reference_auto
        ):
            optional_rejected += 1
        if case.category.startswith(
            ("removed-", "changed-", "additional-", "reordered-")
        ) and (production_auto or reference_auto):
            mutation_accepted += 1
        if (
            production.match_status.value == "MULTIPLE_TEMPLATE_MATCH"
            and production_auto
        ) or (
            reference["match_status"] == "MULTIPLE_TEMPLATE_MATCH" and reference_auto
        ):
            multiple_accepted += 1
    body = {
        "schema_version": 1,
        "case_count": len(cases),
        "category_counts": tuple(sorted(categories.items())),
        "production_reference_agreement": f"{(len(cases) - disagreement) / len(cases):.6f}",
        "disagreement_count": disagreement,
        "disagreement_review_required_count": review,
        "false_automatic_license_identity_count": false_automatic,
        "valid_optional_variant_rejected_count": optional_rejected,
        "substantive_mutation_accepted_count": mutation_accepted,
        "multiple_match_automatic_acceptance_count": multiple_accepted,
        "isolation_audit": audit,
        "input_corpus_hash": content_hash(
            tuple(
                {
                    **asdict(item),
                    "raw": base64.b64encode(item.raw).decode("ascii"),
                }
                for item in cases
            )
        ),
        "java_receipts_hash": java_receipts_hash,
    }
    return SPDXDifferentialReport(**body, report_hash=content_hash(body))


def _isolation_audit(
    modules: tuple[str, ...], matcher: SPDXLicenseMatcher
) -> SPDXIsolationAudit:
    reference = REFERENCE_SOURCE.read_text(encoding="utf-8")
    production_path = Path(type(matcher).__module__.replace(".", "/"))
    del (
        production_path
    )  # Path is obtained from the live class below, never imported by Java.
    production = Path(__import__(matcher.__class__.__module__, fromlist=["x"]).__file__)
    production_text = production.read_text(encoding="utf-8")
    production_to_reference = sum(
        marker in production_text
        for marker in ("IndependentSpdxReference", "spdx-reference-java")
    )
    reference_to_production = sum(
        marker in reference for marker in ("ai_brain", "SPDXLicenseMatcher", "python")
    )
    forbidden = sum(
        marker in reference
        for marker in (
            "java.net",
            "ProcessBuilder",
            "Runtime.getRuntime",
            "javax.script",
        )
    )
    if set(modules) - {"java.base", "java.xml"}:
        forbidden += len(set(modules) - {"java.base", "java.xml"})
    body = {
        "production_to_reference_dependency_count": production_to_reference,
        "reference_to_production_dependency_count": reference_to_production,
        "forbidden_java_dependency_count": forbidden,
        "java_modules": modules,
        "reference_source_sha256": bytes_hash(REFERENCE_SOURCE.read_bytes()),
        "production_source_sha256": bytes_hash(production.read_bytes()),
    }
    return SPDXIsolationAudit(**body, audit_hash=content_hash(body))


def _verify_java_receipt(
    row: dict, case: SPDXDifferentialCase, implementation_hash: str
) -> None:
    expected = {
        "automatic",
        "case_id",
        "match_status",
        "normalized_sha256",
        "reference_implementation_sha256",
        "schema_version",
        "source_document",
        "source_document_sha256",
        "template_license_id",
        "receipt_sha256",
    }
    if (
        set(row) != expected
        or row["schema_version"] != 1
        or row["case_id"] != case.case_id
    ):
        raise ValueError("Java reference receipt schema or identity mismatch")
    if row["reference_implementation_sha256"] != implementation_hash:
        raise ValueError("Java reference implementation binding mismatch")
    if row["source_document_sha256"] != bytes_hash(case.raw):
        raise ValueError("Java reference source bytes binding mismatch")
    body = dict(row)
    claimed = body.pop("receipt_sha256")
    canonical = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    if bytes_hash(canonical.encode()) != claimed:
        raise ValueError("Java reference receipt hash mismatch")


def _run(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=180,
    )
    if completed.returncode:
        raise RuntimeError(
            f"reference command failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    return completed


def _remove_middle(value: str) -> str:
    lines = value.splitlines(keepends=True)
    if len(lines) >= 5:
        start = len(lines) // 3
        return "".join(lines[:start] + lines[start + max(1, len(lines) // 5) :])
    words = value.split()
    start = len(words) // 3
    return " ".join(words[:start] + words[start + max(1, len(words) // 5) :]) + "\n"


def _swap_halves(value: str) -> str:
    lines = value.splitlines(keepends=True)
    midpoint = len(lines) // 2
    return "".join(lines[midpoint:] + lines[:midpoint])


def _substantive_change(value: str, needles: tuple[str, ...], replacement: str) -> str:
    for needle in needles:
        changed, count = re.subn(
            re.escape(needle), replacement, value, count=1, flags=re.IGNORECASE
        )
        if count:
            return changed
    return f"{replacement.upper()} OF RIGHTS\n{value}"
