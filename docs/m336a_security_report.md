# Network and archive security

The mutation suite covers repository substitution, redirect escape, HTTP downgrade, absent/wrong/malformed checksums, duplicate ZIP paths, traversal, absolute/drive paths, symlinks, encryption, entry-count and size limits, compression ratio, NFC/casefold collisions, conflicting license candidates, malformed license encoding, malformed XML, DTD/entity input, classifier changes, and version/GAV changes.

Archive limits are deterministic: 20,000 entries, 256 MiB total uncompressed, 32 MiB per entry, and 200:1 maximum ratio. ZIP paths and license candidates are canonicalized before use. All implemented mutations fail closed; evidence insufficiency is review-required only in the explicitly modeled license modes.
