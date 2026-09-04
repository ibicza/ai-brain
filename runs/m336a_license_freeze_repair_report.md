# M-33.6a license provenance and freeze repair

## Decision and scope

Outcome: `READY_FOR_FRESH_JAVA_FREEZE_V2` (35/35 mandatory readiness criteria, zero failures). M-33.6a is a development repair of roadmap M-33, not a fresh Java acquisition and not a retroactive Java black-box success. M-33.6b is the next untouched oracle-free Java freeze; M-33.7 remains the final four-domain proof; roadmap M-34 Episodic and Relationship Memory has not started.

No new coordinate pool, selector seed, untouched source JAR/tree, final evaluator, or F/H/E final-freeze chain was created. Only the three already disclosed M-33.6 artifacts and local adversarial fixtures were used.

## Source control and graph

The branch is `exp/stage3-m336a-license-freeze-repair`. Exact ancestry through I16 is E14 `6b0c31e6e6f987216923a66e332370aeeffa9f48` -> F15 `d377a206bb251508b94680dd267f0c5cd02dd2aa` -> H15 `ae86c630a4141dc97cfe97fd4a46d2eeaacc5831` -> E15 `b4f8b881ab15e995c8df9e17e4704f5dec34e028` -> I16 `6cf0cda35b19a3efb97f3e4bcfc78f1b3fdec970`. Every link has one parent and the historical M-33 Outcome-C commit `b94c17dc8b1026fe9e338b5fc0a4926b23d68a39` remains outside ancestry.

The project graph moved from 16,131 nodes / 113,549 edges / 1,066 files at E15 to 16,249 nodes / 115,007 edges / 1,075 files at I16. The exact queries, call paths, exclusions, and graph limitations are recorded in the graph impact map.

## Historical failure and provenance closure

The exact M-33.6 failure was `ARCHIVE_LICENSE_NOT_EMBEDDED`, not `LICENSE_INCOMPATIBLE`: Caffeine's source JAR lacked an embedded license, and the old `_license_receipt` raised before root accumulation and before the selector, so zero final sources were selected. The new generic model separates artifact identity, license evidence, immutable SCM revision linkage, deterministic source correspondence, qualification, and non-semantic audit events.

| Candidate | Evidence mode | Intrinsic result | Java correspondence | Future result |
|---|---|---|---:|---|
| Guava 33.4.8-jre | `EMBEDDED_EXACT_LICENSE` | `VERIFIED` / `ELIGIBLE` | 615/615 exact | `DENYLISTED` |
| Commons Collections 4.5.0 | `EMBEDDED_EXACT_LICENSE` | `VERIFIED` / `ELIGIBLE` | 359/359 exact | `DENYLISTED` |
| Caffeine 3.2.0 | `POM_PLUS_IMMUTABLE_SCM_LICENSE` | `VERIFIED` / `ELIGIBLE` | 50/50 exact | `DENYLISTED` |

All correspondence has zero unmatched and zero ambiguous entries; the aggregate is 1,024/1,024. Caffeine is development-qualified through its exact POM Apache-2.0 declaration, immutable tag `v3.2.0` -> commit `93d845e58d8e7bf2dfc88a31c5a078bca5bf4dbf`, exact root LICENSE, and exact source correspondence. Incomplete POM-only evidence remains `REVIEW_REQUIRED`; conflicts remain blocked.

All exact GAV/POM/archive bindings passed. Caffeine's source-JAR and POM SHA-256 sidecars were published and verified. Guava and Commons did not publish the four corresponding SHA-256 sidecars, which is recorded rather than fabricated. Six detached signatures were fetched and byte-bound; signer/key trust is explicitly not claimed. The common normalized Apache-2.0 license hash is `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.

Qualification produces one immutable typed receipt per candidate before selection. Optional rejection does not abort other qualification; required failure and unmet global corpus constraints block. The selector is invoked exactly once after qualification, with zero reruns and no parser/evaluator/trust metrics in eligibility.

## Denylist, serialization, and disclosure

All disclosed candidates are permanently excluded from future untouched selection. The M-33.6a denylist contains 3 coordinates, 3 source URLs, 3 archive hashes, 3 POM hashes, 1,024 raw hashes, 1,024 canonical hashes, 3 normalized SCM tree hashes, 16,784 declaration fingerprints, 3 immutable commits, and 3 correspondence hashes. Manifest hash: `075a3d98bb6cd6c88f67e2444a0cd462e90f36c16e97f0b85b89698050ea5848`; provenance matrix hash: `ecabe336cf23bc13e64953f5b29b40dbe98c4e4a2900569352cd8ae70fa54c15`.

The strict role-manifest codec enforces field/schema/enum sets, duplicate-key rejection, canonical ordering, typed tuple conversion, independent hash recomputation, and byte-identical roundtrip. Historical H15 `committed_role_manifest_matches` is true. Typed role/field disclosure claims reduce the nine known false positives to zero while all 20 genuine disclosure mutations remain blocked; the nine role-serialization mutations also remain blocked.

## Historical protocol, security, and quality

The immutable E14 -> F15 -> H15 -> E15 protocol now passes: exact parents/messages, zero merges, H/E path allowlists, zero frozen-code mutations, role manifest match, and zero false disclosure tokens. This does not change the experiment: its outcome remains `OUTCOME_C_BLOCKED` because acquisition stopped before selection/production.

The 18-case provenance/license matrix, 22 archive/network mutations, 20 disclosure mutations, 9 role-serialization mutations, denylist variants, optional/required qualification cases, and all M-33.5/M-33.6 regressions passed. Host substitution, redirect escape, HTTP downgrade, checksum faults, ZIP traversal/collision/symlink/encryption/bomb limits, malformed/conflicting license data, XXE/DTD, classifier changes, and version/GAV substitutions fail closed or remain explicitly review-required.

Exact-I16 results:

- Windows: Ruff PASS; targeted 110 passed in 21.98 s; authoritative full suite 985 passed in 1,192.74 s; slow test 3/3 at 81.203205 / 90.575014 / 89.973172 s; no-torch/no-network PASS; orphan subprocesses 0; clean.
- Karina (`192.168.100.6`, tmux `m336a-license-freeze-repair`): Ruff PASS; targeted 110 passed in 7.36 s; authoritative full suite 985 passed in 327.26 s; no-torch/no-network PASS; clean.
- Platform-independent mechanism and historical reports are byte-identical; difference count 0.

The Windows timeout root cause was tail latency in hundreds of intentionally durable SQLite FactMemory transitions under full-suite filesystem/antivirus contention, not a dead wait, source copy, or repeated rebuild. The measured stage-specific limit is 300 s, with assertions and durability unchanged. Full performance p50/p95/p99, throughput, and peak memory are in the performance report; peak traced memory was 356,138,064 bytes on Windows and 356,094,488 bytes on Karina.

Evidence manifest hash: `bf085ef6ade7d02afff87573d84f566ceab0ebe85a3498e0a2d5165a99064f70`. Readiness gate hash: `fa2e0eb0b6f93f318bdb71d984c97bc5b6b620b986e3fa38e644024aab2572a6`.

No moral, moderation, NSFW, political, ideological, refusal, topic, personality/opinion, internal-reasoning, or answer-censorship policy was added. License/provenance decisions remain technical evidence states only.
