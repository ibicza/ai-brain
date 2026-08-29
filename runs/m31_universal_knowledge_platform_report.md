# M-31 universal knowledge platform final report

Outcome: **A — UNIVERSAL KNOWLEDGE PLATFORM WORKS**.

## Release identity

- Branch: `exp/stage3-universal-knowledge-ir`
- H10: `f7d6b024109094c1136950f36488edfdfd6e9e83`
- Parent chain: H10 -> E9 `e44c073364476d662a0df55d918177aa569d4c54` -> H9 `0da9e8a316698257b7726bc406618ba3e8669e32`
- E10 message: `M-31 exact-SHA universal knowledge evidence`
- Roadmap: `docs/lifelong_cognitive_system_roadmap.md`
- Roadmap SHA-256: `8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`

## Exact gates

- Local exact H10: 796 passed; ruff clean; Outcome A acceptance PASS; CLI, deterministic rebuild, graph, and clean-tree checks PASS.
- Karina exact H10: 795 passed, 1 platform skip; Outcome A acceptance PASS; CLI, independent 30-file rebuild, performance, registry backup/restore, graph, and clean-tree checks PASS.
- The local transcript records one corrected CLI invocation: the first call put the global `--registry` option after the subcommand; the corrected call passed and all remaining checks completed.
- Existing M-25 through M-30 regressions and the M-30 generic freeze are included in both complete pytest runs.

## Functional and security evidence

- Universal IR: 10,000/10,000 canonical round-trips; 5,000/5,000 malformed or tampered records rejected.
- Capability registry: 5,000 cases, 2,500 exact resolutions, all unknown cases returned `NEEDS_NEW_CAPABILITY`; provider substitution fails closed.
- Domain packs: 2,000/2,000 mutations rejected; strict duplicate-key, path/entry, size, schema, graph, provenance, source, capability, approval, and checksum boundaries are tested.
- Chemistry: pack hash `9141046a5cfa227d2f7c9e7e736d8bc6255e1a75755a91d2aa4ba5fe666cdf4f`; 2,000/2,000 catalog entries equivalent; trusted M-29/M-30 artifact diff is empty.
- Fixtures: taxonomy and quantity/equation packs validate and share one runtime with chemistry; 1,000/1,000 interactions pass with zero core changes.
- Generic core: zero chemistry references, no torch import, no runtime network, and no automatic FactMemory or RuleMemory writes.
- Progress/recommendation: concept and prerequisite data are injected from the active pack; stale history remains structurally inspectable but cannot authorize new action.
- Recovery: crash injection covers every coordinated journal stage; pending actions publish at most one authoritative result and do not claim physically exactly-once CPU invocation.
- No moral, moderation, refusal, political, ideological, or topic policy was added.

## Graph and performance

The pre-edit local graph was 8,522 nodes, 79,588 edges, and 504 files. The final local persistent index was 8,745/81,518/551. A clean disposable Karina exact-H10 rebuild was 5,675/54,449/420; both final parsers reported 421 parsed files and 5,676 full-build nodes. The difference is recorded as persistent Windows-path index history rather than presented as a semantic source delta.

Local vs Karina p50/p95/p99 milliseconds:

| Operation | Local | Karina |
|---|---:|---:|
| IR validation (10,000) | 0.1318 / 0.2513 / 1.4005 | 0.071604 / 0.075572 / 0.076955 |
| Capability lookup (10,000) | 0.0069 / 0.0126 / 0.0156 | 0.004058 / 0.004208 / 0.004979 |
| Exercise-family resolution (10,000) | 0.0033 / 0.0061 / 0.0075 | 0.002194 / 0.002294 / 0.002454 |
| Recommendation (10,000) | 0.3338 / 0.6010 / 2.8102 | 0.174318 / 0.178886 / 0.182362 |
| Chemistry conversation (25) | 1505.8636 / 2169.9663 / 2198.5342 | 361.799941 / 363.213878 / 364.375842 |

The machine-readable acceptance files contain every requested operation, throughput, and peak Python memory measurement.

## Limitations and recommendation

Packs remain manually/offline compiled; the two additional packs are structural fixtures, not broad academic competence; Stage 3 does not automatically write FactMemory or RuleMemory; and whole-file rollback prevention still needs an external monotonic release anchor. Capability receipts grant no execution authority.

Recommendation: proceed to M-32 with a bounded source-to-knowledge compiler that emits provisional IR and requires the same validation, capability closure, evaluation, human/trusted-process approval, and exact-SHA installation path.
