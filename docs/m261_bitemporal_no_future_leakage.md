# M-26.1 Bitemporal No-Future-Leakage

FactMemory keeps valid time (`valid_at`) separate from transaction knowledge time
(`known_at`). `make_query` binds an explicit normalized `known_at`; the answer
receipt repeats both temporal bindings.

## As-Of Projection

`transaction_interval_as_known_at(claim_id, known_at)` returns the original
transaction start, the latest status known then, and a terminal transaction end
only when that terminal event occurred on or before `known_at`.

The same upper bound is applied to:

- claim status events;
- source status events;
- evidence attachments;
- conflict creation and resolution events;
- selected/remaining claims from a reviewed conflict resolution.

Consequently a January receipt cannot reveal a February retraction,
supersession, source withdrawal, evidence attachment, resolution, warning, or
`transaction_to`.

## Receipts

Schema-v2 answer hashes bind `valid_at`, `known_at`, transaction/status
projections, source statuses, polarity-specific evidence references, conflict
resolution status, provenance detail mode, memory snapshot, and rendering
version. Changing `known_at` invalidates replay. A v1 answer schema is rejected
instead of being interpreted under v2 semantics.

Historical executions emit `HISTORICAL_QUERY_EXECUTED` with temporal points and
artifact hashes, not source text.
