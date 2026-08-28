# M-29 Educational Architecture

The trusted path is:

`FactMemory/exact chemistry tool -> immutable derivation graph -> deterministic renderer -> exercise -> typed answer -> exact grade -> bounded diagnosis -> hint`.

The generic package is `ai_brain.stage2.education`; chemistry-specific catalogs and graph access live under `ai_brain.stage2.domains.chemistry.education`. Trusted imports do not load torch, training code, checkpoints, web clients, or network clients. Educational state is separate from FactMemory and RuleMemory.

Versions are bound in `education/version.py`; incompatible chemistry, source-chain, tool, exercise, grading, hint, and session dependencies fail closed during replay.
