# M-29.1 PresentedExercise boundary

The public immutable object contains only session ID, exercise ID, language, question, public givens, difficulty metadata, learning objectives, accepted-answer format, schema and presentation hash.

It does not contain the expected answer, graph or lookup hash, counterfactuals, diagnoses, compilation receipt, answer-key hash, provenance internals or split labels. Service creation, controlled GENERATE_EXERCISE and CLI serialization expose only this type.

Internal `ExerciseInstance` remains store/admin-only. The 1,000-case public boundary battery checks dataclass and serialized field names; hidden-answer, graph, counterfactual and split leaks are zero.
