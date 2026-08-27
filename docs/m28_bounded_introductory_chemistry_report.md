# M-28 Bounded Introductory Chemistry Report

## Outcome

Local implementation and acceptance select Outcome A: the bounded educational vertical slice works for approved element facts, formulas, molar mass, mass/amount, entity/amount, provenance, exact routing, explicit confirmation, and deterministic RU/EN rendering.

## Pack

- Sources: IUPAC periodic table 2022, CIAAW standard and abridged atomic weights 2024, BIPM SI Brochure 9th edition version 3.02, reviewed RU translation policy 1.0.
- Entities: 33 elements plus the Avogadro constant.
- Claims/evidence/sources: 310 / 100 / 4.
- Formula grammar: exact symbols, positive subscripts, bounded parentheses; unsupported syntax fails closed.
- Reproducible content hash: `ff37a1e3c3732e03a2382315a73db0925f6099f3c75faf525845715f3a835e7b`.

## Results

Local M-28 acceptance: 1,635/1,635. Golden pack: 30/30. Invalid battery: 130/130 rejected. 10,000-calculation local throughput: 4,552.75/s. Trusted chemistry import is torch-free and network-free.

The isolated source-update simulation preserved the historical oxygen value, exposed the overlapping update as a conflict, rejected a pending pre-update proposal, and replayed the old calculation as `STALE_FACT_MEMORY`.

## Exact-SHA Gates

- Branch: `exp/stage2-chemistry-domain`
- H3: `19c3bd2423eb99df489f03c35e3b3848e627cdbc`
- Local: format/lint PASS, `647 passed` in 590.88 s.
- Karina: format/lint PASS, `647 passed` in 145.79 s.
- Karina rebuild: 310 claims, 100 evidence records, 4 sources; reproducible hash exactly matched.
- Karina acceptance: 1,635/1,635.
- Karina 10,000 calculations: 9,568.49/s; molar mass p50/p95/p99 0.1058/0.1120/0.1355 ms.
- Backup/restore, source-update simulation, result replay, no-torch/no-network, and final clean checkout: PASS.
- Full local/Karina p50/p95/p99 matrix covers pack load, fact query, parser/composition, snapshot creation, conversions, routing, confirmed response, replay, verify, and backup/restore.

M-29 should add educational explanations and exercises only over these verified structured bundles, without widening trusted chemistry scope.
