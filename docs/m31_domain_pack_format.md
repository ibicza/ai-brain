# Domain Pack format v1

Every pack contains `manifest.json`, `knowledge.jsonl`, `concept_graph.json`,
`exercise_families.json`, `capability_requirements.json`,
`adapter_bindings.json`, `evaluation_manifest.json`, `source_bindings.json`, and
`pack_manifest.json`. All closures are hash-bound. The domain name and subject
tags are descriptive metadata only; behavior follows knowledge kinds, exact
capability requirements, and reviewed adapter bindings.

Strict loading rejects missing/unknown files, symlinks, duplicate JSON keys,
oversized resources, wrong schemas/hashes, dangling/cyclic prerequisites,
undeclared cross-pack edges, unsafe identifiers, and incomplete source or
capability closures.
