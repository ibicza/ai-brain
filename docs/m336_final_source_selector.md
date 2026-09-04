# M-33.6 final source selector

The finite metadata-only source-family policy is frozen before F15:

- `com.google.guava:guava:33.4.8-jre` sources, Apache-2.0;
- `org.apache.commons:commons-collections4:4.5.0` sources, Apache-2.0;
- `com.github.ben-manes.caffeine:caffeine:3.2.0` sources, Apache-2.0.

No candidate source body is acquired during Phase 0. After exact F15 is pushed, the
one-shot acquisition command verifies archive provenance and embedded license text,
extracts safely, and ranks eligible callable files by the frozen F15-derived policy.
Selection round-robins source families and cannot observe parser accuracy or an
evaluator result.

The selected corpus must have at least two roots; no root may exceed 80% of callable
targets. Frozen minima are 100 callable files, 2,000 callable targets, 175 receiver
types, 15 packages, 125 overload groups, 75 constructors, 100 generic methods, 100
throws declarations, and 25 nested-member targets. Tests, generated/vendor paths,
`module-info.java`, and `package-info.java` are excluded.

The permanent denylist covers prior archive, raw-source, canonical-text, selected
path/tree, and declaration fingerprints. Raw, newline-normalized, path-renamed,
canonical, or declaration-fingerprint overlap blocks before production.
