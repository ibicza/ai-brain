# M-29 Verified Educational Layer Report

## Outcome

Outcome A: the verified tutoring layer works locally. Derivation graphs, deterministic RU/EN explanations, six exercise families, exact grading, conservative counterfactual diagnosis, five-level hints, event-sourced sessions, replay, CLI, and backup/restore are implemented.

## Versions

- Educational layer 1.0.0 / schema 1.
- Derivation graph, exercise, grading, tutor session schemas: 1.
- Hint/rendering policies: 1.0.
- Chemistry domain 1.3.0 / schema 4 / source chain 4.0.

## Results

- Provenance preflight: 534/534 values, zero mismatch/uncovered.
- Explanation acceptance: 1,300, all correctness invariants 1.0000.
- Exercises: 5,000 unique; deterministic regeneration 1.0000.
- Grading: 10,000/10,000 agreement.
- Diagnosis: 3,000; precision 1.0000, wrong confident 0, ambiguity retained.
- Hints: 2,000 sequences; early leakage 0.
- Session store: checksummed append-only replay and moved backup/restore verified.
- Local performance: 229.523 interactions/s; peak 3,406,937 bytes.
- Optional neural surface: disabled.
- Trusted torch/network use: zero.

## Release State

Implementation is ready for the exact-SHA H6/E6 gates. No moral/moderation/refusal policy was added. The recommended M-30 scope is a bounded conversational tutor plus observable progress memory over these verified artifacts.
