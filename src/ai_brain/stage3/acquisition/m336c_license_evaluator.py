"""Independent source-derived corpus for the M-33.6c SPDX matcher gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.spdx_license import (
    AUTOMATIC_SPDX_MATCH_STATUSES,
    SPDXLicenseMatcher,
)


class LicenseCorpusClass(StrEnum):
    VALID_VARIANT = "VALID_VARIANT"
    SUBSTANTIVE_MUTATION = "SUBSTANTIVE_MUTATION"
    CONTROL = "CONTROL"


@dataclass(frozen=True)
class IndependentLicenseCase:
    case_id: str
    corpus_class: LicenseCorpusClass
    expected_license_id: str | None
    optional_apache_variant: bool
    payload: bytes
    payload_sha256: str
    case_hash: str


@dataclass(frozen=True)
class IndependentLicenseEvaluation:
    case_count: int
    valid_variant_count: int
    substantive_mutation_count: int
    control_count: int
    automatically_trusted_count: int
    correctly_trusted_count: int
    false_automatic_match_count: int
    false_apache_match_count: int
    optional_apache_variant_count: int
    optional_apache_variant_rejected_count: int
    true_conflict_mutation_count: int
    true_conflict_mutation_blocked_count: int
    automatically_trusted_precision: str
    status_counts: tuple[tuple[str, int], ...]
    corpus_manifest_hash: str
    report_hash: str


_APACHE_MUTATIONS = (
    (b"Grant of Patent License", b"Grant of Patent Permission"),
    (b"patent license to make", b"patent suggestion to make"),
    (b"WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND", b"WITH ALL WARRANTIES"),
    (b"You must give any other recipients", b"You may withhold from recipients"),
    (b"Limitation of Liability", b"Unlimited Liability"),
    (b"royalty-free", b"royalty-bearing"),
    (b"irrevocable", b"revocable"),
    (b"Redistribution", b"No Redistribution"),
)


def build_independent_license_corpus(
    matcher: SPDXLicenseMatcher,
) -> tuple[IndependentLicenseCase, ...]:
    """Build labels from declared transforms, never from matcher output."""

    apache = (matcher.snapshot_root / "Apache-2.0.txt").read_bytes()
    appendix_marker = b"APPENDIX: How to apply the Apache License to your work."
    appendix_offset = apache.index(appendix_marker)
    without_appendix = apache[:appendix_offset].rstrip() + b"\n"
    valid = []
    for index in range(500):
        base = without_appendix if index % 5 == 0 else apache
        text = base.decode("utf-8")
        mode = index % 12
        if mode == 0:
            text = text.replace("\n", "\r\n")
        elif mode == 1:
            text = text.replace("\n\n", "\n \n")
        elif mode == 2:
            text = text.replace("Apache License", "APACHE LICENSE", 1)
        elif mode == 3:
            text = text.replace("http://www.apache.org", "https://www.apache.org", 1)
        elif mode == 4:
            text = text.replace("1. Definitions.", "1) Definitions.", 1)
        elif mode == 5:
            text = text.replace("Version 2.0,", "Version 2.0 -", 1)
        elif mode == 6:
            text = "\n" * (1 + index // 100) + text
        elif mode == 7:
            text = text.rstrip() + " " * (1 + index // 100) + "\n"
        elif mode == 8:
            text = text.replace("TERMS AND CONDITIONS", "Terms and Conditions", 1)
        elif mode == 9:
            text = text.replace("(a)", "a.", 1)
        elif mode == 10:
            text = text.replace(
                "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\n",
                "",
                1,
            )
        else:
            text = text.replace(
                "Copyright [yyyy] [name of copyright owner]",
                f"Copyright {2000 + index % 27} Example Organization",
                1,
            )
        # A harmless, deterministic whitespace signature makes all 500 cases unique.
        text = text.replace("\n", " " * (index // 10 + 1) + "\n", 1)
        valid.append(
            _case(
                f"valid-apache-{index:04d}",
                LicenseCorpusClass.VALID_VARIANT,
                "Apache-2.0",
                index % 5 == 0 or mode == 10,
                text.encode("utf-8"),
            )
        )

    invalid = []
    for index in range(500):
        mode = index % (len(_APACHE_MUTATIONS) + 4)
        if mode < len(_APACHE_MUTATIONS):
            before, after = _APACHE_MUTATIONS[mode]
            replacement = after + f" mutation-{index:04d}".encode()
            mutated = apache.replace(before, replacement, 1)
        elif mode == len(_APACHE_MUTATIONS):
            mutated = apache.replace(
                b"3. Grant of Patent License.",
                f"3. Clause Removed mutation-{index:04d}.".encode(),
                1,
            )
        elif mode == len(_APACHE_MUTATIONS) + 1:
            mutated = (
                apache
                + (
                    f"\nAdditional restriction mutation-{index:04d}: "
                    "redistribution is forbidden.\n"
                ).encode()
            )
        elif mode == len(_APACHE_MUTATIONS) + 2:
            mutated = apache.replace(
                b"Apache License",
                "\u0410pache License".encode("utf-8")
                + f" mutation-{index:04d}".encode(),
                1,
            )
        else:
            mutated = apache.replace(
                b"3. Grant of Patent License.",
                f"4. Reordered Patent Clause mutation-{index:04d}.".encode(),
                1,
            )
        if mutated == apache:
            raise ValueError("independent corpus mutation anchor is absent")
        invalid.append(
            _case(
                f"invalid-apache-{index:04d}",
                LicenseCorpusClass.SUBSTANTIVE_MUTATION,
                None,
                False,
                mutated,
            )
        )

    other_ids = ("MIT", "BSD-2-Clause", "BSD-3-Clause", "GPL-2.0-only")
    controls = []
    for index in range(500):
        if index < len(other_ids):
            expected = other_ids[index]
            payload = (matcher.snapshot_root / f"{expected}.txt").read_bytes()
        elif index % 7 == 0:
            expected = None
            payload = (
                f"NOTICE {index}: Apache License is mentioned for attribution only; "
                "this is not a project license grant."
            ).encode()
        elif index % 7 == 1:
            expected = None
            payload = f"Third-party attribution record {index}.".encode()
        else:
            expected = None
            payload = (
                f"Deterministic random prose control {index}: quartz river cobalt."
            ).encode()
        controls.append(
            _case(
                f"control-{index:04d}",
                LicenseCorpusClass.CONTROL,
                expected,
                False,
                payload,
            )
        )
    cases = tuple(valid + invalid + controls)
    if len({item.payload_sha256 for item in cases}) != len(cases):
        raise ValueError("independent license corpus contains duplicate payloads")
    return cases


def evaluate_independent_license_corpus(
    matcher: SPDXLicenseMatcher | None = None,
) -> IndependentLicenseEvaluation:
    production = matcher or SPDXLicenseMatcher()
    cases = build_independent_license_corpus(production)
    trusted = 0
    correct = 0
    false = 0
    false_apache = 0
    optional_rejected = 0
    blocked_mutations = 0
    statuses: dict[str, int] = {}
    for case in cases:
        receipt = production.match(
            case.payload,
            source_document=f"independent/{case.case_id}/LICENSE",
        )
        status = receipt.match_status.value
        statuses[status] = statuses.get(status, 0) + 1
        automatic = receipt.match_status in AUTOMATIC_SPDX_MATCH_STATUSES
        if automatic:
            trusted += 1
            matches_expected = receipt.template_license_id == case.expected_license_id
            correct += int(matches_expected)
            false += int(not matches_expected)
            false_apache += int(
                receipt.template_license_id == "Apache-2.0"
                and case.expected_license_id != "Apache-2.0"
            )
        if case.optional_apache_variant and not (
            automatic and receipt.template_license_id == "Apache-2.0"
        ):
            optional_rejected += 1
        if case.corpus_class is LicenseCorpusClass.SUBSTANTIVE_MUTATION:
            blocked_mutations += int(
                not automatic or receipt.template_license_id != "Apache-2.0"
            )
    precision = correct / trusted if trusted else 0.0
    manifest = tuple(
        (
            item.case_id,
            item.corpus_class,
            item.expected_license_id,
            item.optional_apache_variant,
            item.payload_sha256,
            item.case_hash,
        )
        for item in cases
    )
    body = {
        "case_count": len(cases),
        "valid_variant_count": sum(
            item.corpus_class is LicenseCorpusClass.VALID_VARIANT for item in cases
        ),
        "substantive_mutation_count": sum(
            item.corpus_class is LicenseCorpusClass.SUBSTANTIVE_MUTATION
            for item in cases
        ),
        "control_count": sum(
            item.corpus_class is LicenseCorpusClass.CONTROL for item in cases
        ),
        "automatically_trusted_count": trusted,
        "correctly_trusted_count": correct,
        "false_automatic_match_count": false,
        "false_apache_match_count": false_apache,
        "optional_apache_variant_count": sum(
            item.optional_apache_variant for item in cases
        ),
        "optional_apache_variant_rejected_count": optional_rejected,
        "true_conflict_mutation_count": 500,
        "true_conflict_mutation_blocked_count": blocked_mutations,
        "automatically_trusted_precision": f"{precision:.6f}",
        "status_counts": tuple(sorted(statuses.items())),
        "corpus_manifest_hash": content_hash(manifest),
    }
    return IndependentLicenseEvaluation(**body, report_hash=content_hash(body))


def _case(
    case_id: str,
    corpus_class: LicenseCorpusClass,
    expected_license_id: str | None,
    optional: bool,
    payload: bytes,
) -> IndependentLicenseCase:
    body = {
        "case_id": case_id,
        "corpus_class": corpus_class,
        "expected_license_id": expected_license_id,
        "optional_apache_variant": optional,
        "payload_sha256": bytes_hash(payload),
    }
    return IndependentLicenseCase(
        **body,
        payload=payload,
        case_hash=content_hash(body),
    )
