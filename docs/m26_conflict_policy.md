# M-26 Conflict Policy

Unresolved `SINGLE` conflicts produce `CONFLICT`, all supported competing claims, conflict group IDs, provenance components, and a warning. No ranking score may collapse this result.

Retracting or losing one source does not silently make the other value true. The group remains unresolved and the answer exposes the stale side. Claim supersession/retraction changes active transaction visibility but preserves the historical group.

`MULTI` values coexist unless a future predicate-specific policy says otherwise. M-26 has no automatic conflict winner or resolution inference.
