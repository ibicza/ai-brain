# M-30 fact upstream replay

Fact-derived graphs now embed typed replay descriptors for the question and answer bindings. Replay checks the exact current value, claim/state, evidence, immediate source, derivation, official upstream source, source-chain and FactMemory snapshot. It distinguishes `STALE_DERIVATION` and `STALE_FACT_VALUE`; any mismatch blocks new grading.
