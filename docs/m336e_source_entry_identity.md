# M-33.6e source-entry identity

`SourceEntryId` is the single semantic identity passed from archive inspection to
qualification, census, selection, and production. It binds the candidate family,
source-JAR SHA-256, canonical archive path, raw bytes SHA-256, and canonical-source
SHA-256. `SourceEntryBinding` explicitly maps that identity through archive, SCM,
vault, selected-snapshot, and production-document domains.

Archive and SCM paths are scoped by candidate because unrelated archives may both
contain `module-info.java`. Vault paths, selected paths, and production document
identities are global and collision-free. All domains reject traversal, absolute
paths, drive paths, NUL, normalization duplicates, separator-only duplicates, and
casefold collisions. A selectable source without a verified binding is rejected
before selector reservation.

The binding manifest is hash-bound and sorted by `SourceEntryId.identity_hash`.
Neither a path string nor a host absolute path is selector authority.
