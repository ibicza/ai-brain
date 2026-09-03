# M-33.5 disclosed-corpus development metrics

These exact-I14 measurements were produced only after oracle-free production,
sealing, candidate compilation, isolated installation and standalone replay.
The evaluator used Microsoft OpenJDK 21.0.11 on both Windows and Karina. The
Apache material is disclosed development data; this is not a new black-box
result.

## Location and semantic accuracy

| Measure | Value |
|---|---:|
| Expected declarations | 3,307 |
| Exact location TP / FP / FN | 3,297 / 0 / 10 |
| Location precision / recall | 1.000000 / 0.996976 |
| Exact semantic TP / FP / FN | 3,297 / 0 / 10 |
| Semantic precision / recall | 1.000000 / 0.996976 |
| Correct-location/wrong-content | 0 |
| Per-field semantic mismatches | 0 |

By root, Commons IO located 1,334/1,336 declarations and trusted 1,045;
Commons Lang located 1,963/1,971 and trusted 1,643. By construct, constructors
located 410/410 and methods 2,887/2,897. The evaluator report contains the full
breakdown by source root, Java construct and blocker category.

## Trust, evidence and resolution

| Measure | Value |
|---|---:|
| Correct trusted / wrong trusted | 2,688 / 0 |
| Correct withheld / incorrect withheld | 313 / 306 |
| Trust precision | 1.000000 |
| Trust recall / coverage | 0.897796 / 0.897796 |
| Field evidence required / present / exact | 127,547 / 127,547 / 127,547 |
| Missing / extra / duplicate / wrong evidence | 0 / 0 / 0 / 0 |
| Field-evidence exactness | 1.000000 |
| Resolution oracle agreement | 1.000000 |

Unsupported diagnostic categories retain `N/A` / `NOT_MEASURED`; no empty
denominator was converted into a success rate. Windows and Karina evaluator
reports are byte-identical with report hash
`19cd0f5cbe519fc4e86df1a6aca245b1d17d768155b53c81834e021f13954a4d`.
