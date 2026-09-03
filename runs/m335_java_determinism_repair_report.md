# M-33.5 run report

Exact-I14 Windows and Karina gates passed. The cross-platform difference count
is zero, the candidate pack and component manifest are byte-identical, all
51/51 V3 criteria passed and all 51/51 gate mutations blocked. Decision:
`READY_FOR_FRESH_JAVA_FREEZE`.

I14 is `f738eaf1b4c710776c0cc37b13d8c07dac248158`. E14 is the commit
containing this report; its exact SHA is returned after commit because a Git
commit cannot contain its own content-addressed identity.

The complete narrative is `docs/m335_java_determinism_repair_report.md`; the
machine-readable evidence is under `runs/m335_final_gate/`.
