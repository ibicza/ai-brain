# M-24.1 RuleMemory Migration

Normal RuleMemory loading never accepts checksum-less files. To migrate a trusted legacy schema-v1 file:

```powershell
uv run ai-brain-stage1 migrate-rule-memory --source legacy.json --destination rule-memory-v101.json --evidence-output migration.json
```

Migration requires the exact legacy root and record schemas, validates every canonical program/specification/status/evidence binding, and property-verifies every active rule. It refuses an existing destination. Success writes a checksummed production file, preserves the source bytes as `.legacy.bak`, and emits source/destination hashes, record count, reverified rule IDs, schema version, paths, and timestamp.

Malformed legacy input, invalid evidence, failed verification, or a destination collision aborts without silently normalizing or installing data.
