# M-26.1 Actor Authority

Trusted operations use `ActorIdentityType` with exactly `HUMAN`,
`TRUSTED_PROCESS`, and `MODEL`.

## Guard

One `_trusted_actor` guard is used for approved evidence, proposal review, claim
approval, claim supersession/retraction, source status changes, and manual
conflict resolution. It requires a nonblank identity and a valid non-MODEL enum.
Reserved model identities are rejected case-insensitively even when paired with a
nominal HUMAN type. Invalid or case-tricked types also fail through the same guard
and emit `FACT_ACTOR_REJECTED`.

## Model Evidence Policy

MODEL_INFERENCE may be stored, cited, or contradict a claim, but it cannot be the
only normal trusted SUPPORTS source and never counts as an independent
corroborating family. Approval binds:

- all source and evidence hashes;
- supporting evidence hashes;
- reviewer identity and typed authority;
- `independent_non_model_support`;
- policy and schema versions.

Commit re-evaluates these dependencies. Changing source kind, support polarity,
evidence content, actor fields, or the reviewed proposal after approval makes the
approval stale and prevents the write.

The acceptance/security matrix covers blank and whitespace identities, MODEL
actors, reserved identity spellings, invalid lower-case actor types, model-only
support, disguised model sources, and independent official support.
