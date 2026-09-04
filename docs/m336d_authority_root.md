# M-33.6d frozen authority root

M-33.6d accepts exactly one externally supplied authority statement. Its byte SHA-256 is `87839e541c1e62ad4311ee20d2a3249271155aca79b8ba0d36b7563d4ce31806`; the derived root hash is `661230e8b7866b92d6da98157d25077e95c37fed187a145edb2c8c9159f166a1`.

The root permits sealed local retention, local analysis/evaluation, derived knowledge and public reproducible evaluation. It permits publication of derived packs and metrics. Raw-source and source-excerpt publication remain denied. Content hashes establish integrity only; registry issuance establishes the authorization lineage.

Derived receipts bind the root/policy, F19, acquisition run, candidate, coordinate, repository, source-JAR/POM/SCM/source-tree/vault identities and parent. Child scopes must preserve parent order and be a strict subset or equality. Runtime-created alternative roots, widening, reordered scopes and cross-binding replay are rejected.
