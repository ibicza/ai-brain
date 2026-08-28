# M-29.1 performance report

Windows development measurements on CPU:

- Offline compilation: 2,000 entries/receipts and 1,900 receipt-bound tool executions in 165.551317 s. This is excluded from runtime throughput.
- Verified catalog load: 2,000 entries in 14.466293 s.
- Runtime: 10,000 mixed interactions in 52.038757 s, 192.1645 interactions/s, hidden chemistry executions 0.

Runtime stage totals: presentation 1.253 s/1,100; graph verification 2.339 s/1,100; plan 2.721 s/1,100; trusted text 3.727 s/1,100; parsing 0.115 s/1,100; grading 1.151 s/1,100; independent diagnosis 1.128 s/1,100; hints 2.093 s/1,100; semantic store verification 1.498 s/100; live replay 35.824 s/100; transition 0.165 s/1,000.

Live replay dominates because each sample performs live provenance plus full store/session validation. Final exact-H7 Windows and Karina measurements are stored as E7 JSON/evidence.
