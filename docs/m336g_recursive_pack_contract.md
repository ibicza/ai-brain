# M-33.6g recursive candidate-pack contract

`JAVA_PUBLIC_PACK_ENTRY_CONTRACTS` freezes the exact required and optional file set, media types, maximum sizes, and per-entry contract hashes. `pack_manifest.json` binds every other entry's relative name, SHA-256, contract hash, the registry hash, pack tree hash, and public replay commitment hash.

Validation rejects unknown files, directories, symlinks/reparse points, duplicate JSON keys, noncanonical JSON/JSONL, CRLF framing, private roles/fields, nested Java excerpts, complete base64/hex source, filesystem paths, file URIs, home-relative paths, and traversal. Domain loading independently validates typed records, graphs, source bindings, aliases, and manifest closure.

`run_java_public_pack_contract_validation` composes the inherited 14/14 producer and 41/41 variant gate with the internal pack-entry denominator. The current source-free pack has 11/11 covered entry producers and 11/11 produced variants, with zero unknown entries, uncontracted public artifacts, or ambiguous contracts.

Adversarial tests cover old and renamed source fields, deep nesting, reversible source encodings, encoded gzip/ZIP payloads, private roles/manifests, unknown binaries, Windows drive/forward-slash/UNC/extended paths, POSIX paths, file URIs, home-relative paths, traversal, exception strings, and nested lists.
