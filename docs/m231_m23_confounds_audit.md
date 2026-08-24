# M-23.1 M-23 Confounds Audit

M-23 baseline commit: `8e1c3cd`; frozen backend: `stage1-acquisition-v1` -> `11b573e`.

| confound | frozen source location | retest treatment |
|---|---|---|
| alpha_unique_binding_gap | src/ai_brain/rules/grammar.py:235 | addressed in isolated M-23.1 pipeline |
| calibration_not_fail_closed | src/ai_brain/language_to_spec/model.py:527 | addressed in isolated M-23.1 pipeline |
| confidence_ignores_fields | src/ai_brain/language_to_spec/model.py:331 | addressed in isolated M-23.1 pipeline |
| deterministic_holdout_preprogrammed | src/ai_brain/language_to_spec/deterministic.py:20 | addressed in isolated M-23.1 pipeline |
| exact_order_sensitive_ast_eval | scripts/m23_language_to_spec.py:374 | addressed in isolated M-23.1 pipeline |
| finite_answer_json_control | src/ai_brain/language_to_spec/json_control.py:52, src/ai_brain/language_to_spec/json_control.py:123 | addressed in isolated M-23.1 pipeline |
| incomplete_text_complete_target | src/ai_brain/language_to_spec/generator.py:310, src/ai_brain/language_to_spec/generator.py:311 | addressed in isolated M-23.1 pipeline |
| language_family_coupling | src/ai_brain/language_to_spec/generator.py:547, src/ai_brain/language_to_spec/generator.py:553 | addressed in isolated M-23.1 pipeline |
| oracle_clarification | scripts/m23_language_to_spec.py:285 | addressed in isolated M-23.1 pipeline |
| silent_byte_truncation | src/ai_brain/language_to_spec/model.py:136 | addressed in isolated M-23.1 pipeline |
| trained_heads_ignored | src/ai_brain/language_to_spec/model.py:81, src/ai_brain/language_to_spec/model.py:278 | addressed in isolated M-23.1 pipeline |
| typed_parser_byte_not_bpe | src/ai_brain/language_to_spec/model.py:66, src/ai_brain/language_to_spec/model.py:136 | addressed in isolated M-23.1 pipeline |

Original artifacts are hashed in `runs/m231_m23_baseline_snapshot.json` and were not overwritten.
