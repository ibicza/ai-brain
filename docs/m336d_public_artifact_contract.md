# M-33.6d public artifact contract

The versioned registry declares a unique path pattern, role, media type and recursive field contract for every core freeze/H19/E19 artifact. JSON must be strict UTF-8, canonical, LF-only, duplicate-key-free, finite and free of unknown nested fields. Arrays may require non-empty, unique and sorted members.

Paths reject traversal, absolutes, drive paths, non-NFC text, duplicate logical names and casefold collisions. Raw archives, Java source and excerpts, credentials, environment secrets, local paths, and source bytes hidden as direct text, base64 or hex are rejected. The ten core contracts cover the freeze manifest; acquisition, qualification, selector, production-summary, candidate-pack-summary, vault-manifest and H19-seal evidence; and final evaluation/readiness. Their content hashes, row hashes, denominators, ordering and cross-field bindings are recomputed by the validator. The actual candidate pack is a directory of typed JSON/JSONL artifacts, not a synthetic SQLite file. The registry's binary path enforces role, media type, magic, size and exact hash whenever a declared final artifact is binary; no M-33.6d core artifact is mislabeled as generic octet-stream.

The H17 adapter remains separate and read-only. Fresh contracts are not widened to accept historical artifacts.
