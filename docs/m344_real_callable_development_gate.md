# M-34.4 real-callable development gate

The pre-F13 real corpus is disjoint from the frozen final families. It combines
untouched Jackson 2.18.2 sources with a small Java 21 stratum (`Arrays.java` and
`Map.java`) used to supply real generic-method diversity. Package metadata is
excluded from callable counts. Synthetic target count is zero.

Frozen minimums are 40 callable files, 1,000 callables, 100 receiver types, 10
packages, 75 overload groups, 40 constructors, 75 generic methods, 75 throws
declarations, and 20 nested-member targets. Required real-only quality is exact
location precision, at least 0.95 location recall, exact semantic precision, at
least 0.95 semantic recall, exact trust precision, zero wrong trusted, at least
0.80 trust coverage, and exact trusted field evidence.

The measured Windows/Karina combined report and byte-identity receipts are
recorded under `runs/m344_development_gate/` before F13. Diagnostic categories
record expected, observed, trusted, and withheld counts. Any zero denominator is
N/A / `NOT_MEASURED`; synthetic challenge coverage is separate and does not
inflate the real headline.

## Measured pre-freeze result

Windows and Karina independently measured 166 real callable files, 3,525
callables, 221 receiver types, 15 packages, 348 overload groups, 261
constructors, 76 generic methods, 1,228 throws declarations, and 396 nested
members. There were zero package-info callable files and zero synthetic targets.

Both platforms produced 3,525/3,525 exact locations, 3,525/3,525 exact semantic
contents, 3,525 correct trusted, zero wrong trusted, and 136,485/136,485 exact
field-evidence receipts. Location, semantic, trust, coverage, and evidence ratios
are all `1.000000`.

Platform-independent combined hashes are:

- production outputs: `e111a416d69e365870847b76aeb5cfbc033f15b325e1250fc3b02ad895e6a7bb`;
- evaluator reports: `5d68bed4f3a8f0dd33747458124301290af4369af47bd64f3d0f54d92b394dd6`;
- candidate packs: `0da62feb5426085f0d44d12d5b890f8e317c80f556f4a95cf4141e1fc6a9ca4c`.

All 12 required mutations blocked. All 35 mandatory criteria passed on both
platforms, deriving `READY_FOR_FRESH_FREEZE`. The production file audit observed
zero golden reads, standalone replay passed without goldens, and the recursive
production-to-evaluator dependency count was zero.
