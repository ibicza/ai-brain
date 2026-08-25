# M-25 Stage-1 Release Dependency

## Frozen Boundary

- release tag: `stage1-v1.0.1`
- release code commit: `4e9520a16bd3aeb7579ea92ce44060fd7f1a705a`
- evidence commit, deliberately excluded from the branch base: `4ca35d54abfbbd979282331d8c41006b07bedf67`
- Stage-1 version: `1.0.1`
- RuleMemory schema: `1`
- workflow artifact schema: `1`
- ProgramSpecification schema: `1`
- execution limits version: `1`

The M-25 branch was created directly from the release code commit. Stage-1 source and semantics are unchanged. `ai_brain.stage2.version.ensure_stage1_compatible()` rejects any imported Stage-1 version other than `1.0.1`.

## Imported APIs

The trusted Stage-2 path imports only these Stage-1 contracts:

- `ProgramSpecification`, `RuleMemory`, and `RuleRecord`;
- `InstalledRuleReceipt`, `ExecutionLimits`, and immutable workflow artifacts;
- `Stage1Service.execute()` and its bounded execution/audit behavior;
- `parse_controlled_language()` and strict specification validation;
- content/specification hashing and frozen version constants.

Supported families remain exactly `NOOP`, `CLEAR`, `DRAIN`, `MERGE_TWO`, `MERGE_THREE`, and `DROP_THEN_TRANSFER`. M-25 adds no primitive, register, family, neural execution path, rule synthesis path, or automatic installation path.

## Compatibility Adapter

The frozen parser classifies an unknown register `E` as contradictory and can classify an unknown operation with a missing destination as ambiguous before it reaches the operation check. Stage 2 therefore applies a narrow request-domain precheck for explicitly unsupported operations, register `E`, negative values, and unsupported language. The adapter changes only Stage-2 routing status; it does not alter Stage-1 parsing or execution.

## Import Audit

`import ai_brain.stage2` imports no `torch`, tokenizer, training, dataset, hidden evaluator, or learned-retrieval module. Learned retrieval lives in the explicitly opted-in `ai_brain.stage2.learned` research module.
