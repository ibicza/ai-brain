# M-33.6j.1 readiness lineage repair

The historical exact-R25b readiness command requested a second parent from a
normal one-parent commit and exited with code 128. A first-parent depth of two
is not a durable replacement: at R25b it names F24, while at the corrective
R25c it names R25a.

The repaired authority builds a typed, immutable policy from the frozen F24,
R25a and R25b identities plus the current implementation SHA supplied by the
readiness request. It derives the ordered first-parent sequence, each parent
row, merge count and commit-subject hashes from real Git objects. It rejects a
different live HEAD, changed parent, omission, insertion, reorder, merge,
unrelated base, detached unrelated HEAD, dirty worktree, changed frozen subject,
shallow history and a content-rehashed but non-derived receipt at the
`GIT_LINEAGE_VERIFICATION` layer.

Q25 qualification uses two levels. The qualification-input tree contains raw
receipts, including the derived lineage receipt, but excludes the readiness
result, final Q25 manifest and post-commit receipt. The readiness result binds
that input-tree hash. A final staging builder then adds the readiness result and
a manifest that states the exclusion rule without embedding the final tree hash.
The final staging hash remains in an external receipt, and the post-commit
verifier compares every committed blob with the pre-scanned bytes.

No acquisition, selector or evaluator behavior, candidate pool, trust policy,
threshold, publication policy, or source-leak exception is changed by this
repair.
