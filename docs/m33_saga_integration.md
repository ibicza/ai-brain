# M-33 saga integration

Both the generic tutor and legacy M-30 production turn path use
`TutorSagaCoordinator`. One operation ID crosses education, progress,
conversation, and public-response publication. Each committed store stage is
idempotent, inspected after write, and followed immediately by a journal
advance carrying an immutable stage receipt.

The journal persists checksummed operation state and receipt chains. Restart
recovery inspects authoritative stores, reconstructs completed stages, resumes
the first missing stage, and publishes once. It never treats an in-memory return
value as authority.

Development tests inject crashes before and after each of the three store
writes, before and after each journal advance, and before and after public
publication. They then reopen every database and assert one operation, one
conversation turn, three stage receipts, and no pending recovery. The legacy
path has a separate persisted recovery test through the same coordinator.
