# M-25 Safe Dispatch and Security Report

## Dispatch Binding

A query and result produce a pending `SkillSelectionReceipt`. Execution is refused until `CONFIRM_SELECTION` records confirmer identity/type. Dispatch then revalidates query/result hashes, candidate-list hash, registry version/hash, full RuleMemory hash, current active SkillRecord, semantic/specification hashes, proposal, installed receipt, and execution limits before calling frozen `Stage1Service.execute()`.

The successful acceptance smoke dispatched `DRAIN A -> B`, halted under Stage-1 limits, emitted both audit layers, and produced hash-bound selection, dispatch, and Stage-1 execution receipts.

## Negative Security Battery

Automated tests reject:

- tampered registry root, checksum, nested record type, and modified SkillRecord;
- corrupt primary without explicit backup recovery;
- orphan, semantic duplicate, deprecated rule, stale RuleMemory, and stale registry;
- missing confirmation and unrelated rule/receipt;
- changed installed receipt and changed RuleMemory after selection;
- changed candidate list and assistive result falsely marked exact;
- selection replay against another query and dispatch replay against another state;
- ambiguous, contradictory, unsupported, or unknown controlled requests;
- candidate selection absent from the returned list.

The learned retriever object has no RuleMemory or dispatch write API. Its result declares `LEARNED_BI_ENCODER_ASSISTIVE`, always sets `exact_match=false`, and recommends review or synthesis only. Neural output can reach execution only through the same explicit selection receipt, confirmation, and full exact dispatch revalidation as any other assistive candidate.

## Audit Privacy

Stage-2 events bind query/input, registry, memory, candidate, receipt, rule, state, and execution hashes. Raw sensitive input is not duplicated in the audit payload. Failed dispatches record typed failure class and hashes before re-raising.

## Result

Wrong automatic skill selection, ambiguous auto-selection, unknown auto-selection, deprecated/stale selection, unrelated dispatch, and unconfirmed execution were all zero in acceptance/tests. This satisfies the M-25 safe-dispatch blocker.
