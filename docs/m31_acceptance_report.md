# M-31 acceptance report

Exact-H10 local and Karina scaled acceptance result: PASS. It covers 10,000 IR round-trips, 5,000
malformed IR rejections, 5,000 capability resolution/mutation cases, 2,000 pack
mutations, all 2,000 chemistry catalog entries, 1,000 fixture interactions,
registry backup/restore, unsupported capability handling, no-chemistry static
scan, byte-identical rebuilding of 30 generated files, three 10,000-operation
hot-path suites, and the complete requested performance operation list. Exact
machine-readable output is `runs/m31/local_acceptance.json`.

The complete exact-H10 suites produced 796 local passes and 795 Karina passes
with one platform skip. Logs, JSON, rebuild evidence, graph evidence, and the
final report are under `runs/m31_final_gate/` and
`runs/m31_universal_knowledge_platform_report.md`.
