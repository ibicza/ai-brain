# M-33.6e selector feasibility

The hard target is 180 files, with at most 63 from one root and at least three
roots. Frozen disclosed rehearsal quotas are 120 method-bearing files and 30
constructor-bearing files.

`prove_selector_feasibility` computes a deterministic dynamic-programming witness
over root capacity and construct contributions. It does not compute selection
ranks or a final file list. The proof fails unless total capacity, balanced
capacity, root count, construct quotas, and simultaneous allocation all pass.

Only a verified, feasible census/proof pair permits
`SELECTOR_INVOCATION_RESERVED`. An infeasible proof raises before that event. The
selector binds the census, proof, binding manifest, freeze subject, pool, vault,
qualification, and seed; it records one invocation, zero reruns, and zero
evaluator/golden/trust-metric reads.
