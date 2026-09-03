# M-33.5 canonical source ingestion

Acquisition schema 2 computes and validates normalized POSIX relative paths
before document construction. It rejects symlinks, duplicate normalized paths,
NFC collisions and cross-platform casefold collisions, then sorts by exact
UTF-8 path bytes and raw SHA-256. Document IDs are content-derived from schema,
bundle ID, relative path and raw bytes hash.

`imported_at` and `created_at` remain audit metadata but are excluded from
document and bundle semantic hashes. Absolute roots, drive letters, caller
order, directory creation order, locale, timezone and hash seed cannot affect
semantic identity. Schema-1 bundles use the explicit legacy hash verifier;
historical rebuild orchestration must opt into `canonical_identity=False`, while
new Java ingestion defaults to schema 2. Schema-2 artifacts are not silently
interpreted as v1.
