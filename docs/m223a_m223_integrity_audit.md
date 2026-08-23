# M-22.3a M-22.3 Integrity Audit

M-22.3 is frozen unchanged. The corrected experiment records these exact leaks in commit `f653759`:

- target fingerprint lookup: `scripts/m223_stage1_acquisition_validation.py:440-445`;
- mutation tautology: `scripts/m223_stage1_acquisition_validation.py:587-589`;
- empty-spec RuleMemory writes: `scripts/m223_stage1_acquisition_validation.py:642-647` and `722-727`;
- target-behavior novelty scoring: `scripts/m223_stage1_acquisition_validation.py:767-796`;
- benchmark imbalance: `datasets/m223_stage1_validation/manifest.json` records 6,694/6,700 eight-clause programs;
- stale report SHA: generated analysis says `9aaefab`, while the final M-22.3 commit is `f653759`.

M-22.3a replaces these measurements; it does not rewrite the old artifacts.
