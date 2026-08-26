# M-26 Preflight Compatibility

## Assistive Identity

`full_trace_equivalent` is now true only for an exact structural route. Deterministic fuzzy/assistive candidates have no requested `ProgramSpecification`, no equivalence class, and `full_trace_equivalent=false`. Final-state substitutions remain explicitly structurally different and false.

## Learned Checkpoints

New research retriever checkpoints use checkpoint schema 2 and bind `skill_registry_schema_version=3` plus `compatibility=CURRENT`.

M-25.1 checkpoint schema 1 artifacts were trained against SkillRegistry v2. Default loading now fails with both markers:

- `ARCHIVAL_RESEARCH_ONLY`
- `REBIND_OR_REEXPORT_REQUIRED`

Historical M-25/M-25.1 analysis scripts pass `allow_archival_research=True` explicitly. That opt-in permits research replay only; it does not provide v3 routing or dispatch authority, change the frozen blind benchmark, or rebind the checkpoint.
