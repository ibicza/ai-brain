# M-33 independent golden method

Goldens are authored from immutable source snapshots in a workspace that does
not import acquisition, proposal, compiler, or runtime modules. A reviewer
records document identity, line/location, expected segment/proposal kind,
epistemic character, exact typed fields, byte spans, applicability,
capabilities, conflicts, allowed abstentions, and held-out answer semantics.

The golden schema binds `reviewer_method`, `source_location`, `rationale`, and a
content hash. Production proposal IDs are forbidden as golden join keys because
they are compiler outputs. The independent evaluator joins expected and actual
items by immutable document identity and exact source location, then computes
all denominators itself. Expected metric values are not accepted as input.

Held-out tasks use `HeldoutTaskSemanticKey`: operation, target, unknown,
normalized givens, units, conditions, and language-independent answer meaning.
Exact semantic duplicates are rejected; wording, ordering, ID, language, and
timestamp do not create uniqueness. Near-duplicate clusters are reported and
remain separate from the exact count.

Goldens are frozen before the production compiler output is inspected. Any
later correction is an explicit review artifact with old/new hashes and cannot
alter the already reported black-box result.
