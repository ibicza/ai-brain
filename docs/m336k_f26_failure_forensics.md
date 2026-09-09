# M-33.6k F26 failure forensics

## Historical boundary

F26 is immutable at `6a8c226371d478f7c92fb86345bda85265c3323a` and remains
`OUTCOME C — BLOCKED`. Its acquisition ledger contains one reservation, one
start, zero completions, one failure, and zero reruns. Selector and evaluator
invocations are both zero. M-33.6k never repairs, completes, or replays that
ledger.

The external preservation receipt accounts for all 66 candidate directories and
7,436 files (381,730,794 bytes). The preserved-vault manifest is verified before
each R27 rehearsal, and the rehearsal writes to a separate destination.

## Blocking archive

The blocking candidate is family `koloboke-api`, coordinate
`com.koloboke:koloboke-api-jdk8:1.0.0`. Its source JAR contains 39 duplicate
canonical-path groups. Every group is classified as
`DUPLICATE_CONFLICTING_REGULAR_FILE`:

- both entries are regular files;
- payload hashes differ;
- there is no directory/file conflict;
- a first-entry and last-entry ZIP reader can select different payloads;
- no group is unclassified.

Public evidence contains only hashes, ordinals, sizes, ZIP metadata, CRCs, and
the typed classification. It contains neither raw filenames nor source payloads.

## Root cause and repair

The F26 provider inspected the archive inside `_acquire_one()`, caught the
candidate-local error, retained the archive, and returned. The later fresh
preflight inferred eligibility from the retained file and independently called
the legacy archive inspector again. That second exception escaped the candidate
boundary and terminated the global protocol.

R27 replaces this split interpretation with one authoritative V2 inspection and
a sealed `CandidateArchiveInspectionBinding`. Later indexing and census consume
the stored inspection result. A terminally rejected candidate cannot be
re-enabled by scoped qualification and cannot enter the source index, census, or
selector.

## Policy decision

Only compatible repeated directory entries may be accepted. Duplicate regular
files are never silently selected, including byte-identical duplicates.
Conflicting duplicate regular files, file/directory conflicts, normalization
aliases, unsafe paths, symlinks, encryption, malformed archives, limit breaches,
and conflicting license material remain fail-closed candidate decisions.

This is an archive provenance and integrity policy. It adds no moderation,
refusal, topic, ideological, or personality policy.
