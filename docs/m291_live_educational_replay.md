# M-29.1 live educational replay

Replay loads only typed validated artifacts, verifies the exercise/spec/graph/receipt binding, then checks live authority.

Chemistry tool results reuse `replay_chemistry_result()`. Fact results re-read current claim, evidence and source state. Replay separately checks domain, FactMemory, source chain, compilation receipt, graph, answer key, grading/hint policy and event-sourced session integrity.

Typed statuses distinguish stale domain, FactMemory, claim, evidence, source, upstream source, source chain, tool, spec, receipt, answer key and policies from invalid source, graph, artifact or session.

The acceptance battery performs 100 live mutations across domain, FactMemory, source chain, tool policy, claims and sources. No stale artifact is CURRENT and every case reports the expected stale reason.
