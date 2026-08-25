# M-25.2 Semantic Dispatch Security Report

## Exact Route

All 89 installed specifications were searched under both scopes. The resulting
matrix was `178/178`: every result was `EXACT_MATCH`, every selected structural
hash equalled the requested hash, and no canonical substitution occurred.

The existing trusted regressions remain:

- structural retrieval: `89/89`;
- controlled RU/EN: `356/356`;
- cross-language equality: `1.0000`;
- full structural dispatch: `89/89`;
- unsafe automatic selections: `0`.

## Equivalent-Only Integration

Successful reviewed integrations cover MERGE_TWO, MERGE_THREE, and a singleton
NOOP final-state normal form. Each case follows:

1. exact structural member is unavailable;
2. full-trace search returns `NO_MATCH`;
3. final-state-only search returns `FINAL_STATE_EQUIVALENT`;
4. generic confirmation is rejected;
5. special reviewed confirmation is recorded;
6. dispatch revalidates current registry, RuleMemory, class, candidate, receipts,
   and execution limits;
7. executed final state satisfies the requested final-state semantics;
8. dispatch receipt records that the execution trace is structurally different.

## Negative Matrix

The following cases fail closed:

- ordinary confirmation for an equivalent candidate;
- changed scope;
- changed requested structural hash;
- changed selected structural hash;
- changed equivalence-class hash;
- full-trace request using an equivalent-only candidate;
- DROP/order-sensitive substitution;
- stale RuleMemory or candidate membership;
- changed candidate list or installed receipt;
- learned result claiming exact or final-state authority.

## Audit Events

Equivalent routing emits dedicated events:

- `FINAL_STATE_EQUIVALENT_FOUND`;
- `EQUIVALENT_SELECTION_REVIEWED`;
- `EQUIVALENT_SELECTION_CONFIRMED`;
- `EQUIVALENT_SKILL_DISPATCHED`;
- `EQUIVALENT_SKILL_DISPATCH_FAILED`.

Events bind hashes and decisions without logging full sensitive state. The
trusted import remains CPU-only and does not import `torch`.

## Learned Router

No model was retrained and no blind benchmark was reopened. Learned results
cannot set exact authority, declare final-state equivalence, choose scope,
write RuleMemory, or bypass the reviewed confirmation and dispatch path.
