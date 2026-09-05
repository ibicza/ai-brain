# M-33.6d final report

## Decision

**OUTCOME C — BLOCKED.** M-33.6d remains part of roadmap M-33. M-33.7 remains the final four-domain proof, and roadmap M-34 Episodic and Relationship Memory has not started.

The immutable chain is E18 `38082dd1eab82ebfff46ad3c55f5021068909f83` -> R19 `3199c02356de6e7cc9e261504e30f336dd6f09ea` -> F19 `845f65056805acd7517ba4959d38d7d3df8ad7ff` -> H19 `a9527e4731255c4a717cf34e9619ca5c8d07dc66` -> E19 (this evidence commit).

## Proven before and at freeze

- Frozen authority-root hash: `661230e8b7866b92d6da98157d25077e95c37fed187a145edb2c8c9159f166a1`; statement SHA-256: `87839e541c1e62ad4311ee20d2a3249271155aca79b8ba0d36b7563d4ce31806`.
- Authority forgeries accepted: 0. R19 adaptive mutations: 10,260/10,260 rejected. H17 exact mapping: 36/36.
- Independent Java SPDX source hash: `9b5a6f49bc4e6e01896f5dbe3969826104b1a905cf51e9093d665ce773d33587`; disclosed differential: 10,800/10,800 agreement, all false-accept/rejection counters zero.
- Candidate pool: 24 optional families, 23 organizations, zero required candidates, zero pre-F19 source-body bytes. Pool hash: `7ad761e5656d9c5f7d89f38efc4a9be0e208396f884826667aeb52cf62d2b481`.
- Local-cache exclusions: `awaitility`, `hikaricp`, `jakarta-inject`, `jna`, `maven-artifact`, `vavr`.
- Freeze manifest hash: `86c8bba0676f1fa9643d6fe5cf8d382a6bdb4155561be3663b5d082de258cb21`; public contract registry hash: `46912eb8b97bfef3090e753ffba16c98de95dc9c34b9914a703a0688b8a6df53`.

## One-shot acquisition and qualification

Exactly one global acquisition and one selector invocation occurred; selector reruns are zero. All 24 acquired candidates were appended to the disclosure registry. The vault has 4,469 files and 4,390 Java files. Its portable byte-sorted tree hash is `e8d6eae2b740643d4a77277e9b165d2bdfe308ea80cad30fad87eea244102150`, identical on Windows and Karina with zero physical byte differences.

All 12 overlap identity classes are zero. Five roots are analysis-eligible with 410 eligible Java entries: errorprone-annotations 28, failsafe 103, jctools-core 112, jetbrains-annotations 31, and modelmapper 136. Publication-root counts are raw source 0, source excerpt 0, derived pack 5, and metrics 5. The other 3,980 Java files are not analysis-eligible.

The legal inventory found 94 documents, strict unclassified count zero, and 43 unknown-role documents that conservatively force review. Nineteen candidates have complete SCM correspondence; five are incomplete. Exact per-candidate decisions are in `h19/qualification_decisions.json` and summarized in `docs/m336d_candidate_qualification.md`.

## Blocking boundary

The selector's separate callable-source filter produced fewer than three ranked roots and raised before emitting a selected manifest. Selected files and roots are zero; the selector cannot be rerun. The frozen vault verifier also fails on a host-order/portable-order mismatch, and the frozen public contract rejects its own acquisition report. Exact H19 quality then exposes a frozen M-33.6c test that assumes the disclosure registry can never grow beyond six entries.

Production was not started. Proposal count, pack hash/tree, compilation, replay, production seal, independent semantic/trust metrics, wrong-trusted count, installed runtime, and production semantic cross-platform comparison are all `NOT RUN` or not measured.

## Public safety and recommendation

The full leak scan found zero fresh-source leaks across 4,390 Java inputs and 181 public files. No raw source, archive, extracted Java, source excerpt, raw license document, local absolute vault path, credential, or key was committed.

Do not begin M-33.7. Create a new pre-freeze M-33.6e repair that (1) validates callable-root availability before freeze, (2) canonicalizes vault path ordering identically in manifest construction and verification, (3) aligns acquisition-report output with the strict public contract, and (4) replaces the historical six-entry assertion with an append-only registry invariant. Then repeat the untouched proof with a genuinely new pool. Roadmap M-34 remains unstarted.
