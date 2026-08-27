# Current-State Chemistry Knowledge Policy

Production calculations consume only current, uniquely supported FactMemory
claims. Snapshot v2 binds claim records, status events, evidence, source records,
source status events, derivations, policies, manifest, and FactMemory snapshot.

New calculations fail closed for retracted/superseded claims, inactive sources,
conflicts, or contradicting evidence. Pending proposals are invalid after any
bound state change. Replay reports a granular reason instead of recomputing.

The six-scenario simulation covers official update, source retraction, claim
retraction, reviewed supersession, contradicting evidence, and extractor change.
Reviewed supersession preserves the historical claim while restoring a unique
current answer. No mutation restores a retracted source; restoration is a new
reviewed source and claim chain.
