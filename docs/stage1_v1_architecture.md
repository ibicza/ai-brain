# Stage-1 v1 Architecture

Stage-1 v1 is a deterministic, CPU-only rule acquisition and execution service. Its trusted path is:

1. strict form/JSON, canonical DSL, or controlled RU/EN input;
2. immutable proposal and bounded clarification;
3. human-readable review;
4. deterministic known-family compiler or frozen public generic CEGIS;
5. independent property verification;
6. explicit hash-bound approval;
7. atomic RuleMemory installation;
8. exact external-state execution and append-only audit.

The production package is `ai_brain.stage1`. It does not import torch, tokenizers, training code, datasets, runs, neural frontends, or hidden evaluators. The exact DSL semantics are implemented in the pure `ai_brain.rules.ast` module and retain the frozen M-21 behavior.

The six supported families are `NOOP`, `CLEAR`, `DRAIN`, `MERGE_TWO`, `MERGE_THREE`, and `DROP_THEN_TRANSFER`. Variables are `A` through `D`, bound to `R0` through `R3`. The only primitives are `MOVE_ONE`, `DROP_ONE`, and `HALT`.
