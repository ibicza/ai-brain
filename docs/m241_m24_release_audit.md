# M-24 Release Audit

Baseline: `stage1-v1.0.0` at `937f1133d17fdae9012308d329534b881cdf6e09`.

The M-24.1 audit confirmed nine release-hardening issues without changing the frozen architecture:

1. Trusted execution accepted unbounded register totals and retained an action per step.
2. Committed acceptance metadata referenced the base commit and the report still described a completed gate as pending.
3. Program specification and workflow JSON readers allowed coercion and unknown fields.
4. Approval followed candidate generation without a mandatory review of the verified AST and evidence.
5. An installed proposal was not bound to the exact installed rule.
6. Audit payloads lacked the complete hash lineage and execution failures were not recorded.
7. RuleMemory accepted schema-v1 documents after removal of `content_sha256`.
8. Immediate contradiction classification covered only part of the frozen RU/EN synonym matrix.
9. The `ai-brain stage1` convenience route loaded the broad development CLI before dispatch.

M-24.1 addresses these as a narrow v1.0.1 hardening patch. It adds no registers, primitives, families, neural components, tokenizers, model checkpoints, or unrestricted language behavior.
