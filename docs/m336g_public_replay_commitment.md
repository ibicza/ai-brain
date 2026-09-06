# M-33.6g public replay commitment

`JavaPublicReplayCommitment` replaces the current public dependency `java-production-closure.<hash>` with `java-production-replay-commitment.<hash>` and is written as `java_replay_commitment.json`.

It binds the deterministic run, selected and source-entry manifests, a path-independent aggregate source closure, release/parser/compiler identities, compiler policy and report, compilation trust gate, evidence policy, field evidence, proposal manifest, trust closure, and expected production-artifact manifest. It contains no bytes, excerpts, encodings, source/vault paths, executable paths, or host identities. Its canonical JSON is platform neutral.

The R20/R21 source-bearing verifier remains callable for historical evidence, but no current production pack writer calls it.
