# M-33 cross-domain black-box report

The canonical final report is `docs/m33_cross_domain_blackbox_report.md` in the
same evidence commit. It records Outcome C, exact F12/H12 boundaries, source and
license inventory, independently calculated metrics, safe-withheld pack/runtime
results, Windows and Karina exact-H12 gates, security and performance evidence,
the evidence-only diff, and the recommendation not to proceed to M-34.

Key result: the frozen evaluator found 832 wrongly automatically source-entailed
Java proposals and the frozen ordinary compiler failed with a conflicting
semantic identity. No wrong proposal was installed, all 500 safe-withheld tasks
abstained correctly, and no frozen-core tuning followed source reveal. That is
safe failure, but the task's explicit decision rule requires Outcome C.
