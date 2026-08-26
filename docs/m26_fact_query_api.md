# M-26 Fact Query API

Use `FactMemory.make_query(...)`, then `FactMemory.query(query)`. Exact subject ID or exact normalized RU/EN label/alias is required.

Statuses: `EXACT_SINGLE`, `EXACT_MULTI`, `CONFLICT`, `NO_FACT`, `AMBIGUOUS_ENTITY`, `UNKNOWN_ENTITY`, `UNKNOWN_PREDICATE`, `STALE_ONLY`, `RETRACTED_ONLY`, and `INVALID_QUERY`.

Every bundle binds query hash, memory snapshot, claim/evidence/source hashes, conflict hashes, temporal intervals, trust tiers, corroboration counts, warnings, and rendering version. Query IDs are one-use. Replay reports `CURRENT` or `STALE_SNAPSHOT`.

The trusted core emits structured data and deterministic RU/EN rendering only; it does not generate free-form answers.
