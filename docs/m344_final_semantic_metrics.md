# M-34.4 final semantic metrics

Outcome: `OUTCOME_C_BLOCKED`.

The oracle-free production pipeline completed on 3,299 real callable targets and sealed production output hash `2f6820dbffa82a0cd091245f378d7aa474cbd9178c5d34d68d481568429d84c4` in memory. Candidate-pack compilation then failed closed with `ValueError: approved proposals contain a conflicting semantic identity`.

The independent javac evaluator was intentionally not started after that failure. Therefore final location precision/recall, semantic precision/recall, per-field semantic mismatches, resolution-oracle agreement, diagnostic precision/recall, and all oracle-denominator metrics are `N/A (NOT_MEASURED)`. No PASS is inferred from an empty denominator.

The production conflict report contains 48 illegal-duplicate-signature conflicts. Separately, candidate alias analysis found 6 conflicting trusted semantic aliases, including erased/generic collisions in `MutableBoolean` and `Validate`. Exact proposal IDs, hashes, aliases, blocker categories, and locations are preserved in `evaluation/m344_final_java/blocked_result.json` and `evaluation/m344_final_java/production_counts.json`.

Because the failure occurred before oracle creation, there is no physical evaluator census, semantic golden manifest, evaluation confusion matrix, or evaluator report in H13.
