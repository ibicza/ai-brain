# M-28.1 Chemistry Integrity Run Report

Implementation and policy summary: `docs/m281_chemistry_integrity_report.md`.

Final H4: `6344bd2860ccc354196a41ab99895b4d59042859`.

Exact-H4 checks:

- source chain: VERIFIED;
- acceptance: 2,475/2,475;
- independent reference: 100%;
- source/update scenarios: 6/6;
- local pytest: 691 passed;
- Karina pytest: 691 passed;
- local 10,000 mixed calculations: 201.78/s, p50 4.676 ms,
  p95 9.572 ms, p99 18.063 ms;
- Karina 10,000 mixed calculations: 503.04/s, p50 1.990 ms,
  p95 3.812 ms, p99 3.862 ms;
- Karina official reacquisition: 4/4 exact hashes;
- Windows/Linux derived extracts and derivations: byte-identical;
- torch loaded: no;
- runtime network required: no.

Outcome A. Exact logs and machine-readable evidence are under
`runs/m281_final_gate/`. E4 is the evidence-only commit containing this report.
