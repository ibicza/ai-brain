# M-34.3 integrity audit for M-34.4

This is a historical audit; M-34.3 evidence is not rewritten.

1. `src/ai_brain/stage3/acquisition/java_pipeline.py::run_java_trust_pipeline`
   accepts `golden_manifest`, `golden_seal`, and `evaluation_config` and verifies
   the seal before binding trust.
2. `bind_java_trust` calls `_goldens_by_physical` and `_golden_exact`; physical
   and semantic expected results therefore participate in a trusted decision.
3. Golden IDs and hashes enter the legacy `JavaTrustDecision`,
   `JavaTrustClosure`, `TrustBoundProposalBatch`, and
   `java_replay.py` artifacts.
4. Consequently, M-34.3 automatic-trust metrics describe an oracle-assisted
   trust path, not an independent production predictor.
5. `scripts/m343_build_java_corpus.py` selects its 50 OpenJDK inputs with
   `name.endswith("/package-info.java")`; none contributes a callable target.
6. A real-source file count is therefore not a real-callable denominator. The
   callable census was supplied predominantly by generated synthetic files.
7. `OPENJDK_PROVENANCE.json` identifies OpenJDK 25.0.2, while the frozen symbol
   inventory and javac oracle use Java 21 / `--release 21`.
8. `scripts/m343_pre_freeze_acceptance.py` labels mechanical approval as
   `ActorIdentityType.USER`.
9. Conflict recall is demonstrated against seeded duplicate bindings rather
   than naturally observed duplicate identities.
10. Some diagnostic categories have zero development support. They are N/A or
    `NOT_MEASURED`, never empirically passed by an empty denominator.
11. The legacy freeze verifier consumes caller-created path/hash snapshots.
12. Its caller-controlled scope and string-prefix checks were insufficient for
    the real F13/H13/E13 boundary, including prefix-confusion risks.

M-34.4 retains the old API for historical compatibility but introduces a
separate production authority. No M-34.3 evidence, tag, or commit is modified.
