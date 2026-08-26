# M-26 Bitemporal Semantics

Valid intervals use `[valid_from, valid_to)`. Null bounds mean unbounded. Adjacent intervals do not overlap.

Transaction visibility begins at `recorded_at`. Supersession/retraction events close normal visibility at their event time without deleting the claim. Source status is independently time-indexed.

- CURRENT: current transaction view and current valid-time slice.
- VALID_AT: world-time slice at the supplied date/datetime.
- KNOWN_AT: database belief state at the supplied transaction timestamp.
- VALID_AT + KNOWN_AT: conjunction of both dimensions.

Dates compare at UTC midnight. Datetimes require an offset and normalize to UTC. Retroactive corrections are new assertions recorded later with past valid intervals.
