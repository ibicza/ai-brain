# M-29 Verified Educational Layer Report

Outcome A. The local full gate passed with 534/534 provenance values, 1,300 explanations, 5,000 unique exercises, 10,000 exact grading cases at 1.0000 agreement, 3,000 diagnoses with zero wrong confident output, and 2,000 no-leak hint sequences.

Exact H6 `f82dabfd5380a9e7a7a64f8ac9ffde0e47fdbf4e` passed locally and on Karina: 726 full tests and 249 named prior regressions on each host, with clean worktrees. The trusted CPU benchmark completed 10,000 interactions at 234.239/s locally and 393.406/s on Karina. Session replay and moved backup/restore are verified. Neural realization is disabled; trusted imports load no torch and use no runtime network. No moral/moderation/refusal policy was added.

See `docs/m29_verified_educational_layer_report.md` and `runs/m29/final/acceptance.json` for the detailed evidence.
