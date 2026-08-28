# M-29.1 answer-key compilation

`scripts/m291_compile_catalog.py` is the explicit administrative entry point. `catalog_compiler.py` invokes the dedicated compiler, while runtime `catalog.py`, `service.py` and controlled routing have no compiler dependency.

Every catalog entry binds an `EducationalCompilationReceipt` containing compiler and actor identities, policy version, chemistry domain/FactMemory/source-chain snapshots, canonical arguments, tool implementation hash, exact result, graph, exercise spec and timestamp. The receipt hash covers every field. Compilation appends one audit record per receipt.

The development build produced 2,000 receipts and 2,000 audit events. Of these, 1,900 receipts bind exact lower-level tool executions; 100 bind paired factual lookups. Catalog semantic hash: `d89d7fa31475430b68c6be44cb7c57a86cf6a5a68fecd2ab8258ecb3d23c1f83`.

Catalog JSON is written with explicit LF, exactly one terminal LF and no CRLF. V1 catalogs require `REBUILD_REQUIRED_FROM_EDUCATIONAL_V2`.
