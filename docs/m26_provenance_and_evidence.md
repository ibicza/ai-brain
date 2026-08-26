# M-26 Provenance and Evidence

Source metadata never substitutes for source bytes. Snapshots are SHA-256 addressed and verified on every evidence use. Evidence points to a character span, byte span, or RFC 6901 JSON Pointer and binds both snapshot and excerpt hashes.

`SUPPORTS` and `CONTRADICTS` are retained separately. Mirrored documents sharing `source_family` count once for independence. `MODEL_INFERENCE` is not trusted evidence by itself, and `MODEL_PROPOSED` evidence requires independent approval.

Source retraction/unavailability marks dependent claims affected. Claims and evidence remain available to history and audit queries.
