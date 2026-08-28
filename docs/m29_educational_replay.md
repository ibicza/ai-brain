# M-29 Educational Replay

Replay reconstructs the session from its initial event and append-only chain, then checks the spec, instance, graph, chemistry domain, FactMemory snapshot, source chain, tool hash, answer key, grading schema, and hint policy.

Statuses distinguish current, stale domain/facts/source/tool/spec/key/policies, invalid graph, and invalid session. Cross-session chains, changed artifacts, broken checksums, and event-head mismatches fail closed.
