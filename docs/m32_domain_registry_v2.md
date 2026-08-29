# Installed Domain Registry v2

Installation copies exact pack bytes into `packs/<stored_pack_bytes_hash>`. The registry binds approval, provider/capability registry hashes, all resolution receipts, validation/evaluation hashes, dependency pack hashes, status, and an append-only audit event.

Verification reloads stored bytes and rechecks pack structure, approval, receipts, current provider manifests, dependencies, evaluation, and the audit chain. Dependency cycles and undeclared cross-pack targets fail closed. Backup includes both SQLite state and the content-addressed pack sidecar.

`GenericDomainRuntime.verify_currentness()` requires installed authority; structural pack validity alone is never reported as current.
