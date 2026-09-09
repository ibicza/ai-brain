# M-33.6k candidate/global failure boundary

## Candidate terminal model

Each optional candidate ends once with a `CandidateTerminalReceipt`. The receipt
binds candidate policy, run ID, source/POM/SCM receipts, the archive inspection
receipt and binding, retained private artifact hashes, the typed stage and scope,
normalized reason codes, eligibility, and its own content hash.

Expected candidate-local outcomes are represented by closed typed statuses:
`ELIGIBLE_FOR_QUALIFICATION`, `REVIEW_REQUIRED`, `INELIGIBLE_ARCHIVE`,
`INELIGIBLE_PROVENANCE`, `INELIGIBLE_LICENSE`,
`INELIGIBLE_CORRESPONDENCE`, `FETCH_FAILED_OPTIONAL`, `METADATA_DRIFT`,
`DENYLISTED`, and `DISCLOSED_IDENTITY_OVERLAP`.

The coordinator catches only `CandidateLocalFailure`. An unknown programming or
environment exception is neither swallowed nor converted into a candidate
result: it writes the global `ACQUISITION_FAILED` event and propagates.

## Global completion

Candidate rejection is compatible with global completion. The successful ledger
order is:

1. `AUTHORIZATION_VALIDATED`
2. `ACQUISITION_RESERVED`
3. `ACQUISITION_STARTED`
4. `ALL_CANDIDATES_TERMINAL`
5. `ACQUISITION_COMPLETED`

Completion requires one attempt and one terminal receipt per frozen candidate,
no missing or duplicate terminal receipt, no replacement or retry, a sealed vault
manifest, and no unexpected global failure. Pool feasibility is evaluated only
after this accounting is complete.

## Single-inspection invariant

`inspect_source_archive_v2()` enumerates the central directory, validates archive
structure, hashes accepted Java/legal payloads, and produces one deterministic
receipt. `CandidateArchiveInspectionBinding` binds the receipt to candidate,
source-JAR hash, archive policy, accepted-entry manifests, and decision.

Later stages may call the independent typed verifier, but they cannot reinterpret
a rejected archive as eligible. The compatibility preflight explicitly skips a
terminally ineligible candidate before source indexing and census.

## Qualification campaigns

The deterministic dirty-archive campaign covers 32 scenario classes over at
least 5,000 unique ZIP byte sequences and replays every decision. The mixed
candidate campaign covers first, middle, last, consecutive, alternating, 10%,
25%, 50%, all-but-three, and all-candidate failures across the required failure
kinds. Both campaigns require zero candidate-local escapes, retries,
replacements, or selector invocations.
