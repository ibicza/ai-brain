# Cross-store and pending recovery

Progress v3 stores tagged facts: graded-answer hash/correctness, exact hint hash/level, or exact explanation hash. Projections count actual event kinds once; legacy accumulated hint/solution snapshots are ignored.

`TutorSagaCoordinator` surrounds education, progress, and conversation store commits with before/after-write and before/after-journal crash points. Stage receipts bind operation ID, store ID, committed record hashes, time, and stage. Recovery inspects operation-bound store records and never rewrites an already present record.

Pending actions persist exact prepared router response, request, decision, and tool proposal artifacts inside the hashed opaque action payload. A restarted process rehydrates and verifies those artifacts. Expired and changed-dependency actions become terminal; ambiguous `EXECUTING` becomes verified `FAILED` rather than being replayed.

The legacy monolithic M-30 turn path still uses its compatibility orchestration around `_execute`. The strict coordinator is available and tested as a reusable path, but the chemistry-free in-memory generic facade does not claim durable cross-store orchestration.
