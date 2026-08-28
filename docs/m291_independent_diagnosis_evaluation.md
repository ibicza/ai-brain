# M-29.1 independent diagnosis evaluation

The fixture pack `tests/fixtures/m291_independent_student_errors.jsonl` contains 1,200 reviewed, hashed cases and was generated without `chemistry_counterfactuals()` or `COUNTERFACTUAL_CALCULATORS`. Public fixture fields contain no hidden answer material; a separate internal semantic-key binding selects the trusted catalog entry.

Development result: grading-status mismatches 0, wrong confident diagnoses 0, ambiguous 15, unclassified 732, macro precision 0.8421052632 and macro recall 0.2736842105. The full per-category precision/recall and confusion matrix are retained in acceptance JSON.

Recall is intentionally limited: uncertain patterns become partial, ambiguous or unclassified instead of confident guesses. Production-counterfactual plumbing is tested separately and is not presented as independent precision.
