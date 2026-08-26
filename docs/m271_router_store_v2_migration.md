# M-27.1 RouterStore v2 Migration

Run `ai-brain-router --root TARGET migrate --source-root SOURCE`. Source and
target must be separate and the target empty.

Migration verifies schema-v1 SQLite, artifacts and audit chain before copying.
It works in a staging directory, preserves requests, decisions, receipts,
clarifications, tool artifacts, responses and audit history, then verifies the
v2 target before atomic publication. A manifest records source/target hashes,
counts, duration and source preservation. Failure removes staging and publishes
nothing.

Old responses are retained for inspection and marked
`LEGACY_INCOMPLETE_DEPENDENCY_BINDING`. They replay as
`INCOMPATIBLE_LEGACY_ARTIFACT`. Other legacy artifacts are not silently loaded by
the strict v2 CLI deserializers.

