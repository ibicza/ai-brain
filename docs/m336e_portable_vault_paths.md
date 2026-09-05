# M-33.6e portable vault paths

`CanonicalVaultPath` is shared by manifest building, tree hashing, local
verification, transfer verification, and platform comparison. It decodes strict
UTF-8, converts an input-boundary backslash to `/`, normalizes each component to
NFC, and requires a safe relative POSIX path.

Ordering is the unsigned lexicographic order of
`canonical_posix_path.encode("utf-8")`. The portable tree hash is derived only from
canonical manifest rows `(path, sha256, size)`, never host directory enumeration.
Physical traversal proves the exact path set, sizes, hashes, and absence of
symlink/reparse entries.

Fixtures cover ASCII, Cyrillic, composed/decomposed Unicode, non-BMP names,
slash/backslash input, casefold and NFC collisions, prefix paths, identical bytes
at different paths, and deep paths.
