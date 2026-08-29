# M-33 cross-domain metrics

The frozen evaluator result is `FAIL`, hash
`10f2f767c2327b8ab666e5c00b153bedebaa2d267ba5e50fc350684910cd6856`.

| Bundle | Segments | Proposals | Source-entailed | Proposal P/R | Entailment P | Field evidence | Pack eval |
|---|---:|---:|---:|---|---|---|---|
| kinematics | 1,048 | 80 | 76 | 1.000000 / 0.930233 | 1.000000 | 236/240 | PASS 1/1 |
| biology | 447 | 24 | 24 | 1.000000 / 1.000000 | 1.000000 | 72/72 | PASS 1/1 |
| history | 169 | 0 | 0 | N/A / N/A | N/A | 0/0 | PASS 1/1 |
| Java | 10,660 | 883 | 832 | 0.000000 / 0.000000 | 0.000000 | 4,944/4,995 | PASS 1/1 |

The corpus has 12,299 non-document segments. Exact duplicate segment rate is
0.473047 (5,818 duplicates), far above the sealed 0.02 maximum, principally
because line segmentation counts repeated source-code syntax and comment
boilerplate. Capability/conflict denominators are `N/A` where the independent
golden declared none; values were not replaced with 1.0.

There are 500 exact semantic keys and zero near-duplicate clusters. Runtime
results are 500/500 expected outputs, 100% abstention, 0% trusted coverage, zero
wrong trusted answers, and zero installed source proposals. Because the frozen
proposal evaluator reports 832 wrong automatically source-entailed Java items,
M-33 selects Outcome C even though the installation barrier prevented false
trusted answers from reaching users.
