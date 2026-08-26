# M-26.1 Conflict Resolution Lifecycle

`ConflictGroup` remains immutable. Current and historical resolution state is
derived from append-only, hashed `ConflictResolutionEvent` records.

## Resolution Rules

- Source retraction never selects the competing claim. The conflict remains
  unresolved and reports `SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE`.
- Reviewed claim retraction may resolve a group while retaining the remaining
  active claim and full history.
- Explicit reviewed supersession may resolve a group in favor of the declared
  successor relationship.
- Manual resolution or dismissal requires approved evidence, a typed trusted
  actor, a reason, and an explicit event.
- Confidence or ranking scores cannot resolve a group; there is no score-based
  resolution API.

Events bind prior/new status, resolution kind, selected and remaining claim IDs,
evidence IDs, actor identity/type, reason, timestamp, and event hash. Audit events
record proposals, accepted resolutions, and rejected resolution attempts.

`conflicts_at(known_at)` and factual queries project only events visible at that
time. Before a resolution event the answer remains `CONFLICT`; afterward it can
return the reviewed remaining claim with `RESOLVED_CONFLICT_HISTORY`.

For SINGLE predicates, different values over overlapping half-open intervals
create conflicts only when overlap is forbidden. Allowed overlaps and MULTI
predicates coexist without automatic conflict creation. Conflict-key qualifier
differences separate conflict domains.
