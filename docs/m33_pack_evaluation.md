# M-33 executable pack evaluation

M-33 packs contain typed mandatory tests for every record. Each test binds an
ID, evaluator identity and implementation hash, required capability field,
exact input, expected typed status/output hash, record dependencies, and source
dependencies.

The frozen evaluator executes three closure checks per record:

1. typed Knowledge IR validation;
2. complete field-level source-binding dereference closure;
3. declaration of every required capability in the pack manifest.

Unknown operations, malformed test schemas, evaluator-hash mismatch, missing
records/sources, or undeclared capabilities fail closed. Installation executes
the manifest and stores the complete result hash and pass rate in its immutable
receipt. Currentness re-executes evaluation and compares the result hash.
Hidden final tasks are external to the pack and cannot make a pack self-certify.

Legacy schema-v2 string tests remain read-only compatible for M-32 artifacts;
new M-33 packs use typed test objects and cannot take the legacy four-boolean
path.
