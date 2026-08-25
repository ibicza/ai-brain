# M-25.1 All-Skill Dispatch Report

## Trusted Matrix

- exact full dispatch: `89/89`
- representative state checks: `42/42`
- controlled RU/EN representative dispatch: `12/12`
- wrong automatic selection: `0`
- unconfirmed dispatch: `0`

Every structural specification passed exact lookup, pending selection, explicit confirmation, receipt validation, frozen Stage-1 bounded execution, expected final-state comparison, preserve checks, and execution/selection/dispatch hash binding.

The representative family battery includes all-zero, one active source, multiple sources, nonzero destination, nonzero preserved register, count 10, and count 100. It covers NOOP, CLEAR, DRAIN, MERGE_TWO, MERGE_THREE, and DROP_THEN_TRANSFER.

This matrix exposed and fixed a controlled-language integration defect: retrieval signed its internally enriched query instead of the original user query, so selection rejected controlled results as foreign. Results now remain bound to the original query while parsed structure remains exact evidence.
