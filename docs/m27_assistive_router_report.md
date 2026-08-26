# M-27 Assistive Router Report

The frozen research dataset contains 30,000 train, 4,000 validation, 4,000
calibration, 8,000 development, and 8,000 blind examples. Classes and RU/EN
language are balanced independently. Exact prompt intersections from train into
every evaluation split are zero. The manifest hash is
`dd2aa0d1ad60113346b5d368f5e2acf0d13fc6c4806c75948eb8135909e92240`.

The selected deterministic character n-gram baseline reached 0.9905 development
top-1, 0.8271 on the development hard-cross-domain slice, 0.9893 calibration
top-1, and 0.9913 on the single frozen blind opening. Unsupported, ambiguous,
and composite recall on calibration were 1.0000. False exact authority was zero
because assistive output is structurally incapable of becoming exact authority.
The token-overlap baseline reached 0.8796 development top-1.

Post-freeze evaluation code reports calibration macro one-vs-rest AUROC 0.9689,
macro AUPRC 0.9461, known-route recall 0.9779, and hard-cross-domain error rate
0.2108. Confidence-ranked calibration risk was 0 through 90% coverage and
0.0108 at full coverage. These post-freeze metrics did not alter the recipe or
reopen blind labels.

The recipe was frozen before the blind labels were opened; its hash is
`d5f06ca3fda6307d93948eafe710501fbc9dba3cae95f970b60e7f7e215c796c`.
The blind target hash is
`2048463c83b9da9bad1e778c0b56c316ef134dd83ec5ae37ca507a08514f4e54`.
The deterministic baseline has no trainable model seed, so neural multi-seed
training was not applicable and the blind set was not reopened.

The leakage audit found chance-level wrapper-only classification (0.1663), but
length/punctuation-only classification remained 0.4959. This is a real dataset
limitation: assistive scores are useful for candidate ordering, not evidence of
semantic authority.

Assistive outputs are always `ASSISTIVE_CANDIDATES` with manual review. The
trusted router cannot import this package and cannot convert its scores into
`EXACT_ROUTE`.
