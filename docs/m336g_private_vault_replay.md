# M-33.6g private sealed-vault replay

`SealedJavaReplayInputManifest` is private and portable. Each row carries a `SourceEntryId`, canonical vault-relative and selected-relative identities, raw/canonical hashes, byte length, and production document identity. It duplicates no source body and omits the vault root.

`SealedJavaReplaySourceProvider` resolves each row below the out-of-band sealed vault, rejects traversal and link escape, reads and verifies raw hash, canonical hash, byte length, and identity, and only then admits bytes to an isolated temporary acquisition store and compiler workspace.

`m336g_run_sealed_replay.py` starts a fresh process, reruns compiler-aware source-to-knowledge production with evaluator, goldens, and network unavailable, reconstructs a public pack, and requires a zero-difference full file/hash comparison. Its public receipt exposes only commitments, metrics, zero-read counters, and result hashes.
