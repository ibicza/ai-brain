# Role manifest serialization

`load_final_artifact_role_manifest`, `dump_final_artifact_role_manifest`, and `verify_final_artifact_role_manifest` implement the canonical codec. The loader rejects duplicate JSON keys, unknown fields, wrong schema/types, unknown enums, noncanonical paths/order, duplicate or missing bindings, role downgrades, noncanonical JSON bytes, and hash mismatch. JSON arrays become typed tuples and role strings become exact enums.

The manifest explicitly includes its own `role_manifest.json` path as `FINAL_EVALUATION`; its declared paths are schema metadata, not final corpus secrets. Historical H15 roundtrips byte-identically and equals a freshly derived typed manifest without rewriting H15.
