# M-29.1 explanation plan v2

Trusted explanation text is generated from `ExplanationPlan` plus finite RU/EN templates and verified graph fields. Each typed segment declares its graph nodes and permitted fields; segment, plan and final artifact hashes bind the result.

Verification rebuilds the plan and exact text. Added sentences, values, formulas, units, citations, equations, duplicate answers, Unicode numeric confusables and unauthorized conversions fail even when the artifact hash is recomputed.

CONCISE and FULL may expose their permitted graph results. Generic CHECK_ONLY is refused and must be built from `GradingResult`; generic HINT_ONLY is refused in favor of `HintArtifact`. SOLUTION_AFTER_ATTEMPT requires an attempt.
