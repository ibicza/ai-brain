# M-29.1 artifact semantic validation

The session store has a closed registry for exercise spec, internal instance, presented exercise, source result, compilation receipt, derivation graph, explanation plan, explanation, student answer, grading result, hint plan, hint, session and event.

Save and load require a known kind, typed reconstruction, schema check, internal-hash recomputation, key/internal-hash equality and semantic validation. Full verification scans every artifact and validates cross-artifact and event references.

Checksum-valid but semantically invalid graphs, wrong keys, wrong kinds, missing references and inconsistent attempt/exercise/graph relations fail. `EducationalService._load()` cannot return an unchecked dictionary.

V1 session stores are preserved rather than silently migrated. Users must explicitly archive/export them; M-29.1 starts a separate `artifacts/education/m291/sessions` v2 store.
