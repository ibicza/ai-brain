# M-33.6 canonical bundle verification

For canonical Java bundles, `verify_bundle()` reconstructs the canonical order from
NFC POSIX-relative path bytes plus raw-source hash. It independently checks relative
paths, NFC, uniqueness, casefold uniqueness, sorted unique tags, content-derived
document IDs, document hashes, ordered manifest hashes, and the bundle hash.

Absolute roots and drive letters remain acquisition context and never enter semantic
identity. Event timestamps are retained in audit metadata but excluded from document
and bundle semantic hashes.

The mutation suite covers reversed and fully rehashed documents, changed IDs and
paths, non-NFC paths, tag reordering, duplicate and casefold-colliding paths, and
audit-time substitution. Every semantic mutation is rejected; audit-time-only
substitution remains visible while preserving semantic identity.
