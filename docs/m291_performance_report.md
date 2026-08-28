# M-29.1 performance report

Exact-H7 CPU measurements:

- Windows offline compilation: 2,000 entries/receipts and 1,900 receipt-bound tool executions in 184.038459 s.
- Windows verified catalog load: 2,000 entries in 14.172974 s.
- Windows runtime: 10,000 mixed interactions in 55.333848 s, 180.7212 interactions/s, hidden chemistry executions 0.
- Karina offline compilation: 2,000 entries/receipts and 1,900 receipt-bound tool executions in 23.665411 s.
- Karina verified catalog load: 2,000 entries in 4.736628 s.
- Karina runtime: 10,000 mixed interactions in 10.566232 s, 946.4112 interactions/s, hidden chemistry executions 0.

Offline compilation is excluded from runtime throughput. Live replay dominates both runtime profiles because every replay sample performs live provenance plus full store/session validation. Exact stage totals are stored in `local_performance.json` and `karina_performance.json`.
