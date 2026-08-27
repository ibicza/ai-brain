# Upstream Source State

A production binding is usable only while its immediate derived source and every required upstream source are current and `ACTIVE`. Snapshot and result records retain upstream record hashes, snapshot hashes, state hashes, and status-event hashes.

New snapshots and proposals fail closed for retracted, unavailable, replaced, hash-mismatched, or otherwise invalid upstream state. Replay distinguishes retracted/unavailable/stale upstream state, stale derived state, derivation mismatches, policy changes, and source-chain changes.

The acceptance battery performed 30 state transitions over CIAAW, IUPAC, BIPM, and RU-policy chains. All 30 unsafe states blocked use; zero inactive sources were used and zero official retractions were ignored. Five rebuilt clean successor chains were accepted.
