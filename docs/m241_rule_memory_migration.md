# M-24.1 RuleMemory Migration

Normal RuleMemory loading never accepts checksum-less files. To migrate a trusted legacy schema-v1 file:

```powershell
uv run ai-brain-stage1 migrate-rule-memory --source legacy.json --destination rule-memory-v101.json --evidence-output migration.json
```

Migration requires the exact legacy root and record schemas, validates every canonical program/specification/status/evidence binding, and property-verifies every active rule. It refuses an existing destination. Success writes a checksummed production file, preserves the source bytes as `.legacy.bak`, and emits source/destination hashes, record count, reverified rule IDs, schema version, paths, and timestamp.

Malformed legacy input, invalid evidence, failed verification, or a destination collision aborts without silently normalizing or installing data.

## Explicit backup recovery

Read-only operations may use a completely validated `.bak` file when the primary RuleMemory is corrupt. The loaded memory exposes this state through `recovery_source=backup:...`; installation and all other writes remain blocked until an operator explicitly recovers the primary:

```powershell
uv run ai-brain-stage1 --memory artifacts/stage1/rule_memory.json --audit artifacts/stage1/audit.jsonl recover-rule-memory --evidence-output recovery.json
```

Recovery validates the backup before touching the primary, preserves the exact corrupt primary bytes under a timestamped `.corrupt` path, atomically restores the backup, reloads the restored primary, and appends `RULE_MEMORY_RECOVERED` to the audit log. An invalid backup aborts without replacing the primary and records `RULE_MEMORY_RECOVERY_FAILED`.
