# Stage-1 v1 Architecture

Stage-1 v1.0.1 is a frozen deterministic, CPU-only rule acquisition and execution service. Its trusted path is:

1. strict form/JSON, canonical DSL, or controlled RU/EN input;
2. immutable proposal and one bounded clarification round;
3. proposal review;
4. deterministic known-family compiler or frozen public generic CEGIS;
5. static, abstract, and property verification;
6. explicit review of the verified candidate and evidence;
7. hash-bound approval;
8. checksummed RuleMemory installation and immutable installation receipt;
9. receipt-bound, bounded exact external-state execution;
10. hash-chained audit and workflow reconstruction.

The production package is `ai_brain.stage1`; the trusted executable is `ai-brain-stage1`. Neither imports torch, tokenizers, training code, datasets, runs, neural frontends, or hidden evaluators.

The six supported families remain `NOOP`, `CLEAR`, `DRAIN`, `MERGE_TWO`, `MERGE_THREE`, and `DROP_THEN_TRANSFER`. Variables `A-D` bind to `R0-R3`. The only primitives are `MOVE_ONE`, `DROP_ONE`, and `HALT`. M-24.1 changes release safety, not architecture or semantics.
