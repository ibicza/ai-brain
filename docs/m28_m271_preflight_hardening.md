# M-28 M-27.1 Preflight Hardening

The compatibility preflight closes five fail-open edges before chemistry is loaded.

- `DependencySnapshot.rule_memory_hash` is derived from the live backup-aware RuleMemory and the registry is validated against that memory.
- Decimal tool manifests bind `_DECIMAL_RE.pattern` and `_DECIMAL_RE.flags`.
- Expected skill dispatch, registry, bounded execution, RuleMemory, confirmation, and schema failures produce typed `FAILED` responses.
- Conflict-resolution evidence must have been created and attached no later than the resolution event.
- Unified response replay rejects a mismatched response schema even when hashes are recomputed.

Regression coverage is in `tests/test_m28_preflight_hardening.py`. These changes preserve the M-27.1 authority, confirmation, and replay architecture.
