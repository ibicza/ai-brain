# M-33.6h quality report

Exact-R23 Windows: targeted 91 passed; full 1149 passed. Exact-R23 Karina: targeted 90 passed and 1 platform skip; full 1147 passed and 2 platform skips. Ruff format/lint, compileall, Java reference compilation, no-network and no-torch gates passed.

The first Karina full attempt was invalidated by host disk quota exhaustion. Only temporary data created by that attempt was removed; the clean rerun then passed. No tracked source was changed.
