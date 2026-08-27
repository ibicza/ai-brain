# M-28.1 Acceptance Report

Pre-commit acceptance passed 2,475 cases:

| Area | Cases | Result |
|---|---:|---|
| Atomic weights | 264 | 33 elements, 21 single, 12 interval, uncertainty retained |
| Symbols | 33 | zero wrong-case acceptance |
| Formula/reference | 100 | 100% agreement, zero invalid accepted |
| Mass/amount | 500 | 100% agreement |
| Entity semantics | 300 | 100% agreement, formula never discarded |
| Rounding | 48 | zero declared-rounding failures |
| Router | 1,096 | 396 fact, 400 tool, 100 clarification, 100 unsupported, 100 composite |
| Numeric attacks | 84 | zero bypasses/exact routes |
| Authority/security | 50 | zero automatic execution/write/partial composite |

Source chain is verified, runtime network is not required, and torch is not
loaded.

## Exact-SHA Gates

Implementation H4 `6344bd2860ccc354196a41ab99895b4d59042859` passed
`691` tests locally and `691` tests on Karina. Both hosts passed all 2,475
acceptance cases and the six-scenario source/current-state matrix. Karina also
reacquired all four official network snapshots and reproduced all derived files,
derivation records, and `source_chain.json` byte-for-byte.
