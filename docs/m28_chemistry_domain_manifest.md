# M-28 Chemistry Domain Manifest

`artifacts/domains/chemistry/m28/domain_manifest.json` binds domain/schema versions, frozen source hashes, supported elements, FactMemory snapshot, atomic-weight policy, grammar and limits, transitive tool manifests, controlled router grammar, units, rounding, and rendering policy.

`domain_manifest_hash` binds the deployed pack. `reproducible_content_hash` excludes deployment-specific FactMemory UUID/timestamps while binding the deterministic source/policy/tool content. This distinction is explicit because the frozen FactMemory workflow intentionally generates unique audit identities.

An incompatible version, changed source extract, stale FactMemory snapshot, changed tool implementation, or changed policy fails pack loading.
