# M-29.1 trusted educational integrity report

Outcome B — explanations, exercises and grading trusted; diagnosis or hints limited.

Implementation H7: `bebc4d0d150646ac65142cd2e5dad2e049587a88` on `exp/stage2-educational-integrity`. The evidence-only E7 is the commit containing this finalized report and `runs/m291_final_gate/`; its SHA is reported after commit creation.

The precompiled trusted catalog, v2 graph semantics, exact grading, deterministic explanations, live replay, PresentedExercise boundary, semantic store and session state machine pass development acceptance. Runtime hidden execution is zero; a confirmed new calculation executes exactly once through normal authority. No moral/moderation/refusal or topic policy was added.

The catalog contains 2,000 distinct semantic exercises and 2,000 graphs; 5,000 presentations produce 3,932 distinct questions with genuine disjoint manifests. Graph tampering passes 0/2,000, explanation tampering 0/1,000, public leaks 0/1,000 and stale-as-current replay 0/100.

Independent diagnosis is safe but incomplete: 1,200 fixtures, wrong confident 0, precision 0.8421052632, recall 0.2736842105, 15 ambiguous and 732 unclassified. Targeted hints therefore remain restricted to exact diagnoses; generic hints cover the rest. Independently targeted hints were correct in 120/120 cases, and 100 strong-equivalence leakage probes leaked 0 early answers.

At exact H7, Windows and Karina each passed 739/739 full tests and 274/274 prior trusted regressions. Acceptance passed identically on both platforms. Windows measured 10,000 runtime interactions in 55.333848 s (180.7212/s) and compiled the 2,000-entry catalog in 184.038459 s; Karina measured 10.566232 s (946.4112/s) and 23.665411 s respectively. Both rebuilt the trusted catalog byte-identically (`6166b887f2ab434a5e68b90799c3f0b349e2c28dc78d2ad318392f35cda15cef`) with 2,000 receipts, 1,900 receipt-bound tool executions, and zero missing receipts.

The exact gates also verified zero runtime hidden execution, no torch/network imports, semantic artifact rejection and full-store validation, all 30 session transition pairs, CLI public presentation, catalog/store verification, and backup/restore to a moved store. No moral, moderation, refusal, political, ideological, or topic restriction policy was added.

M-30 may proceed with the safe subset: bounded conversational orchestration and observable learner-progress memory, without expanding diagnosis authority.
