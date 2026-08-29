# M-32 source-to-knowledge compiler report

Status before exact-SHA release gates: implementation candidate.

The bounded compiler ingests four materially different local source genres through one generic pipeline. It produces strict IR v2 proposals, preserves provenance and epistemic distinctions, requires explicit review/approval, compiles deterministic provisional packs, and installs only through current provider/capability/domain authority closure.

Windows precommit results: 812 tests passed; format and lint passed. Four bundles produced 643 segments and 636 approved proposals, with zero wrong automatically verified proposals. All 500 held-out tasks passed in the focused M-32 suite. Seven packs are installed in the v2 registry. Provider and capability registries contain nine entries each.

Preliminary outcome: **Outcome B**. The explicit bounded structured grammar compiles without false trusted installation, while narrative/API ambiguity remains review-bound. The legacy M-30 monolithic turn path is not yet wired to the reusable strict saga coordinator, so Outcome A would overstate platform closure. Exact H11 Windows/Karina reproducibility gates, commit IDs, graph-after counts, and evidence-only diff are intentionally deferred to E11 evidence.

Remaining limitations are listed in `docs/m32_limitations.md`. M-33 should use the safe compiler subset with larger black-box materials while keeping the same review and installation boundaries.
