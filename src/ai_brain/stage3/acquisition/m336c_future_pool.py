"""Metadata-only overprovisioning strategy for the future M-33.6d freeze."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class FutureCandidateFamily:
    family_id: str
    organization: str
    coordinate: str
    metadata_probe_fields: tuple[str, ...]
    source_body_inspection_permitted: bool
    required: bool
    family_hash: str


@dataclass(frozen=True)
class QualificationSimulation:
    scenario: str
    candidate_count: int
    failed_count: int
    review_count: int
    eligible_count: int
    eligible_organization_count: int
    minimum_three_roots_survive: bool
    preferred_five_roots_survive: bool
    simulation_hash: str


_FAMILIES = (
    (
        "jackson-databind",
        "FasterXML",
        "com.fasterxml.jackson.core:jackson-databind:2.20.0",
    ),
    ("gson", "Google", "com.google.code.gson:gson:2.13.2"),
    (
        "httpcore5",
        "Apache HttpComponents",
        "org.apache.httpcomponents.core5:httpcore5:5.3.6",
    ),
    ("log4j-api", "Apache Logging", "org.apache.logging.log4j:log4j-api:2.25.2"),
    ("picocli", "Remkop", "info.picocli:picocli:4.7.7"),
    ("reactor-core", "Project Reactor", "io.projectreactor:reactor-core:3.7.9"),
    ("guava", "Google", "com.google.guava:guava:33.4.8-jre"),
    (
        "eclipse-collections",
        "Eclipse Foundation",
        "org.eclipse.collections:eclipse-collections:11.1.0",
    ),
    ("junit-jupiter-api", "JUnit", "org.junit.jupiter:junit-jupiter-api:5.13.4"),
    ("mockito-core", "Mockito", "org.mockito:mockito-core:5.19.0"),
    ("slf4j-api", "QOS.ch", "org.slf4j:slf4j-api:2.0.17"),
    ("joda-time", "Joda.org", "joda-time:joda-time:2.14.0"),
    ("okio-jvm", "Square", "com.squareup.okio:okio-jvm:3.16.0"),
    ("snakeyaml", "SnakeYAML", "org.yaml:snakeyaml:2.4"),
    ("caffeine", "Ben Manes", "com.github.ben-manes.caffeine:caffeine:3.2.2"),
    ("commons-lang3", "Apache Commons", "org.apache.commons:commons-lang3:3.18.0"),
)

_METADATA_FIELDS = (
    "coordinate_existence",
    "pom_bytes",
    "pom_license_declaration",
    "pom_scm_metadata",
    "declared_java_version",
    "checksum_or_signature_endpoint_availability",
)


def future_candidate_families() -> tuple[FutureCandidateFamily, ...]:
    result = []
    for family_id, organization, coordinate in _FAMILIES:
        body = {
            "family_id": family_id,
            "organization": organization,
            "coordinate": coordinate,
            "metadata_probe_fields": _METADATA_FIELDS,
            "source_body_inspection_permitted": False,
            "required": False,
        }
        result.append(FutureCandidateFamily(**body, family_hash=content_hash(body)))
    families = tuple(result)
    if len(families) < 16 or len({item.organization for item in families}) < 10:
        raise ValueError("M-33.6d candidate strategy is not sufficiently diverse")
    if any(item.required or item.source_body_inspection_permitted for item in families):
        raise ValueError("metadata strategy elevated a candidate or source-body access")
    return families


def run_future_pool_simulations() -> tuple[QualificationSimulation, ...]:
    families = future_candidate_families()
    scenarios = (
        ("ZERO_FAILURES", 0, 0),
        ("TWENTY_FIVE_PERCENT_FAILURES", len(families) // 4, 0),
        ("FIFTY_PERCENT_FAILURES", len(families) // 2, 0),
        ("LICENSE_REVIEW_CASES", 0, 4),
        ("SCM_CORRESPONDENCE_FAILURES", 4, 0),
        ("CHECKSUM_ABSENCE", 3, 2),
        ("DUPLICATE_ORGANIZATIONS", 2, 2),
        ("ROOT_CONTRIBUTION_IMBALANCE", 5, 1),
    )
    result = []
    for scenario, failed, review in scenarios:
        surviving = families[failed + review :]
        eligible = len(surviving)
        organizations = len({item.organization for item in surviving})
        body = {
            "scenario": scenario,
            "candidate_count": len(families),
            "failed_count": failed,
            "review_count": review,
            "eligible_count": eligible,
            "eligible_organization_count": organizations,
            "minimum_three_roots_survive": eligible >= 3,
            "preferred_five_roots_survive": eligible >= 5,
        }
        result.append(
            QualificationSimulation(**body, simulation_hash=content_hash(body))
        )
    return tuple(result)
