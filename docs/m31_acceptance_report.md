# M-31 acceptance report

Local scaled acceptance result: PASS. It covers 10,000 IR round-trips, 5,000
malformed IR rejections, 5,000 capability resolution/mutation cases, 2,000 pack
mutations, all 2,000 chemistry catalog entries, 1,000 fixture interactions,
registry backup/restore, unsupported capability handling, no-chemistry static
scan, byte-identical rebuilding of 30 generated files, three 10,000-operation
hot-path suites, and the complete requested performance operation list. Exact
machine-readable output is `runs/m31/local_acceptance.json`.

Prior Stage-2 tests, exact H10 local/Karina results, graph final state, and
evidence-only E10 binding are recorded in the final platform report after those
gates complete.
