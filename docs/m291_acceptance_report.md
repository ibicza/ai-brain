# M-29.1 acceptance report

Exact-H7 acceptance status: PASS on Windows and Karina. Both environments produced byte-identical acceptance JSON at H7 `bebc4d0d150646ac65142cd2e5dad2e049587a88`.

- Authority: hidden runtime execution 0; unconfirmed execution 0; confirmed new calculation 1; 2,000 receipts; missing receipts 0.
- Graph: 2,000 mutations across nine classes; accepted 0. Interval catalog graphs 9; invalid interval accepted 0.
- Explanation: 1,000 text/plan mutations; unsupported additions accepted 0; CHECK_ONLY leaks 0.
- Public boundary: 1,000 cases; hidden answer/graph/counterfactual/split leaks 0.
- Replay: 100 live domain/fact/source-chain/tool/claim/source mutations; stale reported CURRENT 0; wrong stale reason 0.
- Exercises: 5,000 presentations; 2,000 semantic keys; 3,932 questions; 2,000 graph/value combinations; max variants 3; split intersections 0.
- Diagnosis: 1,200 independent fixtures; wrong confident 0; macro precision 0.8421052632; macro recall 0.2736842105.
- Hints: 120 independently targeted; wrong targeted 0; typed leakage accepted 0/100.
- Sessions: 30 state/event cases; invalid accepted 0; valid rejected 0.
- Artifacts: unknown kind, wrong key and checksum-valid semantic tamper all rejected; full store verified.
- Optional neural surface: DISABLED_NOT_EVALUATED. Content restriction policy added: false.

Exact gates: 739/739 full tests and 274/274 prior trusted regressions passed on each platform. Ruff format/check, offline catalog reconstruction, catalog byte comparison, tutor presentation/verification, and moved-store backup/restore also passed. The local and Karina logs and JSON files are committed under `runs/m291_final_gate/` by the evidence-only commit.
