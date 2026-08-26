# M-27.1 Unified Router Hardening Report

## Outcome

Development result: **Outcome A - unified router hardened**. Exact-SHA local and
Karina evidence is added only after the implementation commit is frozen.

## Implemented

- complete versioned dependency snapshots and granular replay reports;
- RouterStore v2 migration and strict current-artifact validation;
- explicit tool implementation manifests covering helpers/constants/policies;
- typed argument canonicalization and bounded Decimal parsing/rendering;
- FactMemory v4 complete conflict partitions and safe supersession membership;
- PREPARED/COMPLETED/FAILED skill and tool response lifecycle;
- bounded failure audits, migration/attack/replay/lifecycle tests and benchmarks.

## Development Checks

- Ruff format/check: PASS.
- Pytest: 623 passed.
- M-27 trusted acceptance: 1317 checks, 89 structured routes, 356 controlled
  routes, 89 dispatches, zero wrong exact routes and zero partial composites.
- M-27.1 hardening acceptance: 42 checks, 8 replay mutations, 7 manifest
  mutations, 14 Decimal rejections and 28 conflict-policy cases.
- M-26.1 conflict regression: 28/28.

## Limitations

Exact language remains finite controlled RU/EN and assistive routing remains
review-only. There are only two bounded local read-only tools, no network or
side-effecting tools, no automatic fact writes/rule installation, no hidden
planner and no autonomous conflict winner. Legacy incomplete receipts are not
trusted. Manifest coverage is explicit rather than arbitrary dynamic-code
attestation. The system is local and single-host.
