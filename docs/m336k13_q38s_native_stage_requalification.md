# M-33.6k.13 Q38S native-stage requalification

Status: `READY_FOR_IMMUTABLE_FINAL_CONTROLLER_PLAN_BOUND_EXECUTION_V13`

Q38S is an evidence-only qualification of repaired implementation `0baa95ef77b0e65d3fd46a3875aec502eb448bfb`.
It preserves immutable Q38 `40aa68d305627dfedefa623cfce6a64fe2564545` and Q38R `ee34ca2bb9e90bbcb5a916af51fefbdffe375158` and does not modify the
superseded generation-1 plan or any of the four non-sparse reservations.

The original pre-freeze blocker was reproduced at the version boundary. The
repair selects the typed v6 verifier, projects privately to v5 exactly once,
then rebinds active parity to the complete v6 binding. Direct v6-to-v5 use and
public serialization of the base projection are both absent.

Windows and Karina exact-quality receipts are PASS with identical source
identity `d724427fa033412f00a76535f2151ded711efc4582fe7496ffe0eac879c45dfb`. The fresh disposable route completed Q-like,
F-like, H-like, and E-like stages with zero wrong-layer acceptance, zero source
leaks, and zero official-route counters.

Generation 1 is recorded as `SUPERSEDED_PRE_FREEZE_PRESERVED` for reason
`V6_NATIVE_STAGE_VERIFIER_ADAPTER_MISSING_PRE_FREEZE`. Ten generation-crossing mutations were rejected;
accepted cases and writes/releases against old generation state are zero.

The generation-2 reservation is fresh, exclusive, non-sparse, and exactly
2563642326 bytes. Its pre- and post-reservation gates are PASS. The
generation-2 private controller root and all future controller outputs remain
absent until the post-Q38S plan-creation phase.

Evidence set hash: `36ba3dce1235f3743c2a2586a94ac894950d1dbd3c7f422f10ce66ef097776ea`.
