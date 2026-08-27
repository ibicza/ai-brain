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

Exact-SHA local/Karina gates and evidence commit are recorded after implementation commit H3. M-29 should add educational explanations and exercises only over these verified structured bundles, without widening trusted chemistry scope.
