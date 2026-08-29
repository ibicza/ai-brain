# Progress and recommendation migration

Concept IDs now come from installed pack exercise-family bindings. Projection
accepts a runtime concept set and the recommender accepts a generic prerequisite
map. The former chemistry-specific progress constants were removed; direct
structural callers may infer concepts from their events, while production always
injects the active pack graph. Production next-task selection constructs
candidates once from the already verified catalog, applies the deterministic
recommender, avoids the most recent semantic key when possible, and publishes its
reason code.

Global attempts, successes, hints, and solutions count unique progress events;
per-concept evidence remains available separately. Structurally valid stale
history is explicitly distinguished from current authority and cannot authorize
new recommendations or progress reset.
