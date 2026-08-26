# M-27.1 FactMemory v4 Migration

FactMemory schema/migration version 4 introduces conflict policy `4.0`. The
normal FactMemory `migrate` command accepts a schema-v3 source and publishes a
separate verified v4 target through staging.

Existing resolution events are checked against group membership and complete
evidence partitions. Events already satisfying v4 become `VERIFIED_V4`. Unsafe
manual or automatic events retain their legacy hash, become
`LEGACY_RESOLUTION_REVIEW_REQUIRED`, and project the group as unresolved for
trusted current queries. Claims, sources, evidence and old event data remain
preserved; missing evidence is not invented.

The manifest includes source/target hashes, verified/review-required counts,
record counts and integrity results. The schema-v3 source remains byte-for-byte
unchanged.

