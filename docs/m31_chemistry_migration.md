# Chemistry migration

`artifacts/domains/chemistry/generic-v1` represents chemistry through generic
records, 20 concepts, prerequisite edges, six exercise-family bindings,
capability requirements, adapter bindings, languages, evaluation policy, and
references to the exact M-29 FactMemory/source authority. It does not duplicate
facts, blobs, formula parsers, tools, or catalog compiler logic.

Ten capability descriptors include the existing exact chemistry tools and
adapters plus generic fixture verifiers. The M-30 2,000-entry catalog is retained;
the generic runtime maps every entry to the same family/concepts and preserves
entry and semantic-key hashes.
