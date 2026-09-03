# M-33.5 disclosed Apache corpus policy

Commons Lang 3.17.0 and Commons IO 2.18.0 are permanently
`DISCLOSED_DEVELOPMENT_REGRESSION_ONLY`. The denylist binds both archive hashes,
240 raw hashes, 240 canonical-text hashes, the H13 tree hash, selected path
manifest, path/raw/canonical triples and per-source normalized declaration
fingerprint manifests.

The final selector unions this denylist into every future policy and compares
both raw and newline-canonicalized Java bytes. Exact bytes, newline-only copies,
renamed identical source and archives with the recorded archive hashes cannot be
selected for a future untouched result.
