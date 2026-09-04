# M-33.6b provenance envelope v2

Schema version 2 binds the Maven coordinate and derived repository path, source and POM digests, redirect and repository receipts, detached-signature state, license claims and exact license texts, an actually verified SCM revision, source correspondence, derived authenticity and license modes, conflicts, semantic identity, audit event, and envelope hash.

The loader rejects duplicate keys, unknown or missing fields, invalid enums, noncanonical JSON, invalid nested hashes, incorrect derivations, and an altered audit or envelope hash. The verifier recomputes semantic identity and policy results. Persisted bytes round-trip canonically. The JSON Schema uses closed nested objects rather than open arbitrary objects.

Both the disclosed rehearsal and the final freeze call `acquire_and_qualify_maven_source_candidates`; the historical M-33.6a builder is not production authority.
