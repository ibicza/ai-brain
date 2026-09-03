# M-33.5 role-aware freeze verification

Immutable roles distinguish final source, receipt, selector, census, production,
oracle, golden and evaluation knowledge from process audits, quality logs,
reports and generic empty results. The protected role set is part of the hashed
manifest; manifests must be complete and exactly reproducible from canonical
paths, so callers cannot relabel or remove protected files.

Protected bytes and disclosed semantic tokens must be absent from F. Neutral
audit bytes may recur. Canonical path validation, Git boundary matching and
symlink rejection remain active; frozen code and exact parent-chain checks are
unchanged.

Exact-I14 verification passed on both Windows and Karina with report hash
`c0876d864c8fc324671ac1812e796de59e7825f13cfa8141fbbce2f1cbe6f52b`
and empty protected overlap. The neutral all-zero audit reuse positive case
passed; all 16 required disclosure mutations were blocked with mutation report
hash `bebcb96a4811887c283ad2259f1799a8a9af43b7a935163bb0e97f5be2dd0d49`.
