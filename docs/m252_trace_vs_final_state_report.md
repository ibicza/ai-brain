# M-25.2 Trace vs Final State Report

## Validation Method

The frozen Stage-1 interpreter executes every multi-member final-state class
with trace capture on ten deterministic valid states. The validator compares
final states and independently reconstructs every intermediate state from the
captured physical action sequence.

## Results

| Measure | Result |
|---|---:|
| Structural skills | 89 |
| Final-state effect classes | 57 |
| Full-execution identity classes | 89 |
| Singleton final-state classes | 41 |
| Two-member classes | 12 |
| Six-member classes | 4 |
| Trace-distinct multi-member classes | 16 |
| Compared structural pairs | 32 |
| Executions in property battery | 640 |
| Final-state mismatches | 0 |

Every multi-member class had at least one state where its programs produced
different action order, intermediate states, and action-stream hashes while
ending in the same register state.

## MERGE_TWO Proof

For a representative pair, both executions halted after nine actions and ended
in the same state. One stream began `M R1 R0`; the other began `M R2 R0`.
Their specification hashes and action-stream hashes differed, while their
`final_state_effect_hash` was identical.

## MERGE_THREE Proof

For a representative permutation pair, both executions halted after sixteen
actions and ended in the same state. One stream began `M R2 R0`; the other began
`M R3 R0`. Intermediate states and action-stream hashes differed.

## DROP Negative Control

`DROP A` then `MOVE B -> C` and the reversed-source program retain ordered phase
constraints in their normal forms. Their final-state effect hashes are distinct.
Neither scope substitutes the reversed program after the exact member is
removed.

## Conclusion

The 57-class normalization is property-verified for final register state. It is
not evidence of complete execution equivalence and is now named and routed
accordingly.
