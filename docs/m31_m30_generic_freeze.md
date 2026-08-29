# M-30 generic integrity freeze

Progress schema V2 records exact educational event and artifact hashes. The
service derives session, catalog entry, semantic key, concepts, grade correctness,
hint level/count, solution state, and timestamps from installed pack and stored
educational authority. Public totals count unique learner actions instead of
copying one action into every attached concept.

`REQUEST_NEXT_EXERCISE` and `REQUEST_PROGRESS` use the production deterministic
recommender over a verified immutable candidate index. No candidate yields
`NO_CURRENT_RECOMMENDATION`, never a random fallback. Stale history remains
structurally verifiable, exportable, backup-able, and restorable, but exposes
`PROGRESS_CURRENT_AUTHORITY_STALE` and cannot recommend or reset progress.

Cross-store turns use a durable saga journal with PREPARED, EDUCATION_APPLIED,
PROGRESS_APPLIED, CONVERSATION_COMMITTED, COMPLETED, RECOVERY_REQUIRED, and FAILED
states. Pending tools use PREPARED, EXECUTING, EXECUTED, FAILED, CANCELLED,
EXPIRED, and STALE. The guarantee is at most one published authoritative result;
physical exactly-once CPU invocation across process death is not claimed.
