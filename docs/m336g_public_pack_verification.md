# M-33.6g public candidate-pack verification

Public-pack integrity and sealed-source replay are separate mandatory proofs.

Integrity uses only pack bytes. It checks the exact required/optional entry set, no unknown file, no link/reparse entry, media type, framing, size, recursive source/path/private-role rejection, per-entry SHA-256 and contract hash, pack tree hash, replay commitment binding, normal `load_pack`, and domain-pack validation. It never reads a vault, source snapshot, private replay manifest, compiler workspace, evaluator, golden, or network.

The exact current entries are `manifest.json`, `knowledge.jsonl`, `concept_graph.json`, `exercise_families.json`, `capability_requirements.json`, `adapter_bindings.json`, `evaluation_manifest.json`, `source_bindings.json`, optional `alias_semantics.json`, `pack_manifest.json`, and `java_replay_commitment.json`.

`java_production_closure.json` and `java_evidence_closure.json` are not allowed current public entries.
