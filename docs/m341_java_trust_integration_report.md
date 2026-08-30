# M-34.1 Java semantic trust integration report

Status: **READY_FOR_FRESH_FREEZE**. This is a development-only hardening result;
no new untouched frozen evaluation was performed and M-33 Outcome C is unchanged.

The implementation is commit `8d6624300c6be664a997ffe69215d4919808064c`
on `exp/stage3-m34-integration-hardening`, based exactly on
`5bfe424f68bfd6c1414c6048cdc4f35f41dd6daf`. The branch remains unmerged.

## Authoritative pipeline

The public `run_java_trust_pipeline` entry point executes immutable bundle
verification, pinned Tree-sitter Java indexing, physical segmentation, AST-driven
proposal extraction, non-authoritative structural verification, independently
recomputed field evidence, independent-golden matching, conflict detection, and
trust-closure binding. `review_proposal` accepts Java approval only from that exact
closure. `compile_provisional_pack` replays the closure against the actual bundle,
segments, proposals, index, goldens and evidence, and emits exact receipt/span/
transformation/identity references.

Trust-bearing parsing uses `tree-sitter 0.25.2` with
`tree-sitter-java 0.23.5`; the pinned grammar source SHA-256 is
`f5cd57b8f1270a7f0438878750d02ccc79421d45cca65ff284f1527e9ef02e38`.
It is offline, does not execute Java, disables annotation processing by design,
and retains UTF-8 byte and line spans. The old regex identity reader remains only
for historical diagnostic compatibility and cannot grant M-34.1 trust.

The sealed golden manifest contains 300 exact positive locations. It is authored
by `scripts/m341_author_java_goldens.py`, a separate Tree-sitter walk with no
`ai_brain.stage3.acquisition` import path. Acceptance only loads the checked-in
JSON and cannot generate, repair, move, or infer golden locations. Re-authoring
independently reproduces the checked-in bytes.

## Development corpus and results

The hash-disjoint corpus has 41 files: 20 synthetic adversarial sources and 21
OpenJDK 22 `java.time` sources, with zero overlap against the eight hash-only
M-33 Java receipts. The index contains 1,146 declarations (1,142 supported),
including 901 methods and 30 constructors. It produced 931 real AST proposals.

| Metric | Result |
|---|---:|
| independently sealed positive goldens | 300 |
| mutated negative locations | 220/220 rejected |
| source-location precision / recall | 1.000000 / 1.000000 |
| proposal precision / recall | 1.000000 / 1.000000 |
| trusted coverage / trusted proposals | 1.000000 / 300 |
| automatic-trust precision / wrong | 1.000000 / 0 |
| withheld proposals | 631 |
| exact field evidence | 4,718 / 4,718 (1.000000) |
| legal overload conflicts | 0; all three `foo` overloads trusted together |
| seeded conflict detection | 2/2 (1.000000) |
| physical duplicates / rate | 0 / 0.000000 |
| lexical repetitions / rate | 74 / 0.064572 |
| duplicate-derived trusted proposals | computed 0 |
| replay/source mutation/tamper matrix | all blocked |
| compiled records/source bindings | 300 / 300 |
| exact compiled evidence dereference | PASS |

Withholding reasons are exact: 628 proposals lacked a sealed development golden,
one local-type member was unsupported, one parameter used ambiguous `Widget`, and
one used unresolved `MissingType`. All three unsupported proposal candidates were
withheld, so safe abstention is 1.000000.

## Exact-SHA and cross-platform gates

Windows at the implementation SHA passed Ruff, 40 targeted tests, and all 836
tests in 1060.30 seconds. Karina used a clean detached worktree at the same SHA,
passed Ruff, the same 40 targeted tests, and all 836 tests in 291.42 seconds.
Neither acceptance loaded PyTorch or used runtime network, Java execution,
annotation processing, FactMemory, or RuleMemory.

Windows and Karina acceptance JSON files are byte-identical, SHA-256
`8caa510a605955de48223aea9d3e637d3c2ef6360b49d107779d16e558ee0443`.
The source index, document, proposal, evidence, identity, decision, conflict,
closure, trusted-proposal, and compiled-pack hashes are recorded in
`runs/m341_java_trust_integration/cross_platform_hashes.json`.

The implementation branch is pushed without merge. The evidence-only commit
contains this report and `runs/m341_java_trust_integration/`; it does not change
production code, tests, fixtures, dependencies, or the implementation SHA.
