# Stage-1 v1 RuleMemory

RuleMemory schema version 1 stores canonical programs, concrete semantic hashes, verification status, complete specification, evidence, version, deprecation state, and provenance.

Writes use a same-directory temporary file, flush and `fsync`, then atomic `os.replace`. An existing file is retained as `.bak`. New files include a SHA-256 checksum over canonical content. Loading validates schema, checksum, record shape, canonical DSL, unique IDs, and semantic hashes. `load_with_backup` uses the validated backup only when the primary is corrupt.

Rule identity is concrete and order-sensitive because `A-D` have fixed external register bindings and ordered phases are observable in execution traces. An active semantic duplicate is rejected. A deprecated rule may be followed by a new semantic version. Deprecated rules cannot execute.
