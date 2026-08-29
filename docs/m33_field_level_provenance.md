# M-33 field-level provenance

`FieldSourceEvidence` is immutable and binds proposal ID, typed field path,
document, exact byte interval, line/page/table location, document and span
hashes, raw text, canonical normalized value, transformation identity/hash,
extraction method, and evidence hash.

Evidence construction searches only the proposal's declared source segments and
selects the narrowest exact literal span. Case, underscore, and hyphen
normalization are explicit transformations. Missing evidence is omitted and
reported as incomplete; it is never widened to the whole segment.

Composite leaves are flattened independently, including parameters, return
types, exceptions, variables, units, relation endpoints, dates, and inline
applicability conditions. Verification re-dereferences the original immutable
blob, checks every byte/hash/location binding, rejects duplicate field paths,
and reports the exact missing set. Pack source bindings contain evidence hashes,
not blanket segment assertions.
