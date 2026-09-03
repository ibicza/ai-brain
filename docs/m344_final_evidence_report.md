# M-34.4 exact-SHA final evidence

## Decision

`OUTCOME_C_BLOCKED`.

M-34.4 is a repair/finalization task for roadmap M-33. Roadmap M-34 Episodic and Relationship Memory has not started. This Java result does not finish the four-domain cross-domain proof; a new successful Java freeze and then a fresh M-33F four-domain run remain prerequisites.

## Exact chain and isolation

- Base: `f83a4b72de5843d699f971932b0dd28c872ab533`.
- F13: `af7657883fdb2c5ce47c3d82798ef7969b747c8c`, `M-34.4 freeze oracle-free Java acquisition`.
- H13: `3f42cb044daadf29f9c1a1c69ca4706f15f8c75b`, `M-34.4 untouched real-Java evaluation`.
- E13: the commit with subject `M-34.4 exact-SHA fresh-freeze evidence`; its exact SHA is verified after creation because a commit cannot contain its own hash.
- Branch: `exp/stage3-m344-oracle-free-java-freeze`.
- M-33 Outcome-C evidence `b94c17dc8b1026fe9e338b5fc0a4926b23d68a39` remains outside ancestry.

H13 changes only `evaluation/m344_final_java/**` and the three permitted source-specific reports. The frozen `src`, `scripts`, `tools`, `schemas`, `tests`, `pyproject.toml`, `uv.lock`, and `.gitattributes` trees did not change after F13. E13 changes only the frozen evidence/report allowlist.

## Oracle-free production and failure

The production API is `run_java_acquisition_pipeline(bundle, store, *, deterministic_run_id, release_identity=None)`. It accepts no golden/evaluator argument. Static import closure has 0 production-to-evaluator/golden dependencies. Its enforced file audit recorded 144,120 reads, 0 forbidden reads, and no oracle/golden path access. Development golden substitution/removal/forgery/unreadable mutations did not alter production output; all 12 full-gate mutations were rejected and pre-freeze gate v2 was READY (35/35).

On the untouched corpus, production completed and sealed its output in memory. Candidate-pack compilation then rejected 6 conflicting trusted semantic aliases with `ValueError: approved proposals contain a conflicting semantic identity`. Both Windows and Karina reproduced this exact fail-closed stage. Oracle creation, evaluator comparison, candidate replay, approval, and installation did not occur.

The same 240 source path/hash pairs were selected on both platforms, canonical tree hash `a1da5983e0ab2ba64614d4e1bd69ada1953dfb3b86b8627dcfc317be89378192`. Counts also match. However sealed production output is not byte-identical: Windows output hash is `2f6820dbffa82a0cd091245f378d7aa474cbd9178c5d34d68d481568429d84c4`; Karina output hash is `c9a0e718a716db7b72ca7401d9a4f2efbb3d5c9410e1613fb96e5338d2f89c50`. Platform path ordering changes bundle/proposal/node identity ordering. This independently fails the cross-platform deterministic-artifact gate.

## Measured evidence

- Java release: exact Java 21 throughout; release-consistency PASS.
- Development real-only corpus: 166 callable files; 3,525 callables; 221 receiver types; 15 packages; 348 overload groups; 261 constructors; 76 generic methods; 1,228 throws declarations; 396 nested targets; 0 package-info callables; 0 synthetic targets.
- Development location and semantic precision/recall: `1.000000`; trust precision/coverage: `1.000000`; wrong trusted: 0; field evidence: 136,485/136,485 exact.
- Final sources: Apache Commons Lang 3.17.0 and Commons IO 2.18.0, Apache-2.0; exact archive hashes are in the inventory and acquisition receipts; prior-corpus overlap: 0.
- Final real-only census: 240 callable files; 3,299 callables; 323 receiver types; 28 packages; 405 overload groups; 410 constructors; 219 generic methods; 549 throws declarations; 290 nested targets; synthetic targets: 0.
- Production-only decisions: 3,162 trusted, 137 withheld, 65 observed blocker categories, internal coverage `0.958472`, 48 production duplicate-signature conflicts, 0 duplicate-derived trusted.
- Final field evidence: required/present/exact 127,617/127,617/127,617; missing/extra/duplicate/wrong 0/0/0/0.
- Process audit: 0 subprocess invocations, socket attempts, source/class executions, annotation processors, and `os.system` attempts; no FactMemory, RuleMemory, SkillRegistry, provider-registry, or domain-registry mutation.
- Final semantic/trust accuracy, resolution agreement, category precision/recall, and zero-denominator categories: `N/A (NOT_MEASURED)` because the independent oracle did not start.
- Candidate/installed pack hash and replay-without-goldens result: `N/A`; no pack was completed or installed.

## Verification

At exact H13, Windows: Ruff PASS, targeted 9 passed, full suite 875 passed in 1158.92s. Karina: Ruff PASS, targeted 9 passed, full suite 875 passed in 316.97s. Graph detect-changes from F13 analyzed 254 changed data/report files with 0 changed symbols, 0 affected flows, and risk 0.00. The frozen graph remains 12,927 nodes, 98,358 edges, 794 files; the pre-M-34.4 baseline was 10,173 nodes, 71,368 edges, 779 files.

The Git-derived verifier is run after E13 exists and the branch/upstream point to it; its exact result is reported in the delivery response. A successful path-integrity verifier does not override the semantic and determinism failures above.

## Limitations and next action

This work evaluates Java callable/API declarations, not arbitrary method bodies or complete Java language semantics. User source is not executed. Zero-count categories remain unmeasured. Exact extraction uses a Java-specific reusable capability. No moral, moderation, refusal, political, ideological, or topic policy was added.

Next: start a new development repair cycle from E13. Make ingestion/identity order platform-canonical and make candidate semantic-identity conflicts a pre-trust/pre-freeze condition. Add this revealed corpus to the denylist, pass the development and cross-platform gates, and use a genuinely fresh final corpus for the next F/H/E freeze. Only after Java passes should M-33F run the fresh four-domain proof.
