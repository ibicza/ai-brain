# M-33.6c readiness evidence v2

`M336CReadinessGate` consumes 14 mandatory typed raw-report classes. Each report has an exact field set and content hash. The loader recomputes counters, ratios, every criterion and the final decision; it does not trust assembler literals.

Tampering with a raw counter or report hash fails report verification. Tampering with a recomputed ratio, criterion, decision or gate hash makes the claimed gate differ from independent recomputation. Empty mandatory denominators fail rather than becoming vacuous passes.

Because this task grants no raw-source publication, a fully passing semantic rehearsal can produce `SAFE_CONSERVATIVE_SUBSET`; raw publication is not silently inferred from successful analysis.
