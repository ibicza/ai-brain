# M-33.6g source and path leak gate

The scanner preserves exact source-JAR, SCM archive, complete Java file, 256-byte source window, complete base64/hex source, raw legal body, and vault-path checks. It also counts private artifact roles, unknown pack entries, public absolute paths, reversible source payloads, and public source windows.

Path detection covers drive paths with either separator, UNC and extended Windows paths, known POSIX host roots, arbitrary absolute values in path-valued JSON fields, file URIs, home-relative paths, and traversal. URLs and Maven coordinates are not filesystem paths. There is no ignore list and no filename exception.

The exact 256-byte detector uses a disk-backed 16-byte source-anchor index on a 128-byte grid. Every possible 256-byte source window contains at least one such anchor. Four bounded NumPy prefilters select candidates, the complete 16-byte anchor is joined in SQLite, and surrounding bytes are compared exactly; hash/filter collisions cannot count as leaks and cannot hide one.

The development production v4 path audit demonstrated the boundary fix: 150,842 reads and 258 unique host-local read identities remain auditable as counts, while serialized host-path fields are zero. Public production JSON path count is zero; full exact-R22 evidence remains pending the authoritative two-platform gate.
