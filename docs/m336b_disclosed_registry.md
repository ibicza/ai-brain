# M-33.6b append-only disclosed Java registry

Future disclosures live under `artifacts/acquisition/disclosed_java`, outside frozen implementation code. Each content-addressed entry binds coordinate/version, URL, source and POM hashes, raw and canonical source hashes, source-tree hash, selected-path manifest, declaration fingerprints, SCM revision, correspondence hash, disclosure reason, originating chain, and entry hash.

Manifests form a previous-hash chain. Verification rejects missing entries, unknown entries, deletion, rollback, truncation, cycles, noncanonical bytes, and reuse of a strong identity with different entry content. The runtime denylist loader combines historical M-33.5 data, historical M-33.6a data, and all verified registry entries.

Every H17-downloaded candidate is appended whether eligible, review-required, rejected, selected, or unselected.
