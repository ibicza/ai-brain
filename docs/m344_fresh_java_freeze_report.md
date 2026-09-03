# M-34.4 fresh Java freeze report

Outcome: `OUTCOME_C_BLOCKED`.

The untouched 240-file Apache Commons Lang 3.17.0 / Commons IO 2.18.0 Java 21 corpus met all diversity minimums and had zero prior-corpus hash overlap. Oracle-free production completed with 3,299 proposals, 3,162 internally trusted, 137 withheld, and exact field evidence for all 127,617 required fields.

The freeze stopped before the independent oracle because candidate-pack compilation found 6 conflicting trusted semantic aliases. Windows and Karina reproduced the blocker. In addition, identical selected source manifests produced different sealed production hashes (`2f6820db…` vs `c9a0e718…`), so cross-platform deterministic artifacts failed. No evaluator metrics, approval, installation, or replay claim is made.

F13 and H13 are `af7657883fdb2c5ce47c3d82798ef7969b747c8c` and `3f42cb044daadf29f9c1a1c69ca4706f15f8c75b`. The exact E13 SHA and post-push Git-derived freeze result are supplied in the delivery response.

M-34.4 remains a roadmap M-33 repair; roadmap M-34 memory work has not started. Repair canonical ordering and semantic-alias conflict handling in a new development cycle, denylist this revealed corpus, then conduct a new untouched Java freeze before M-33F.
