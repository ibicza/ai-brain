# M-30 controlled conversation: Russian

The finite Russian grammar recognizes start, exercise/next exercise, strict answer submission, hint, solution, explanation, progress, language change, confirmation/cancellation, pause/resume and end. Unrecognized bounded text becomes clarification; with an active exercise it is first tested by the strict student-answer parser. Multi-action requests produce `COMPOSITE_REQUIRED` with zero partial execution.
