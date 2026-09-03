# M-34.4 failure forensics for M-33.5

The complete machine-readable record is
`runs/m335_development/conflict_census.json`. It binds six alias groups, 48
historical conflict instances, their proposal/declaration locations and semantic
hashes, with zero unclassified conflicts.

## Six compiler alias groups

| Alias family | Count | Classification | Measured distinction |
|---|---:|---|---|
| `MutableBoolean.<init>(boolean)` | 2 | `CASEFOLD_COLLISION` | `Z` vs `Ljava/lang/Boolean;` |
| `MutableBoolean.setValue(boolean)` | 2 | `CASEFOLD_COLLISION` | `Z` vs `Ljava/lang/Boolean;` |
| `Validate.notEmpty(T)` | 3 | `LEGAL_OVERLOAD_COLLAPSED_BY_ALIAS` | `Collection`, `Map`, `CharSequence` |
| `Validate.notEmpty(T,String,Object...)` | 3 | `LEGAL_OVERLOAD_COLLAPSED_BY_ALIAS` | the same three first-parameter erasures |
| `Validate.validIndex(T,int)` | 2 | `LEGAL_OVERLOAD_COLLAPSED_BY_ALIAS` | `CharSequence` vs `Collection` |
| `Validate.validIndex(T,int,String,Object...)` | 2 | `LEGAL_OVERLOAD_COLLAPSED_BY_ALIAS` | the same two first-parameter erasures |

The compiler used one casefolded dictionary for record identity, dependency
resolution and search. This made valid overload search collisions fatal.

## Forty-eight production conflicts

All 48 are `LEGAL_OVERLOAD_COLLAPSED_BY_UNRESOLVED_SENTINEL`. Every implicated
declaration had already failed type resolution and therefore carried the same
literal descriptor `UNRESOLVED`. The old detector nevertheless treated that
literal as a JVM signature. The source signatures differ in arity and/or source
types, all 49 implicated proposals were withheld for their resolution blocker,
none entered candidate pack compilation, and none is a true source/classpath
collision. The repaired detector never admits an unresolved declaration to the
authoritative identity denominator.

H13 did not export individual field-evidence receipt hashes in its sealed
evaluator-facing output; the census records this absence rather than inventing
hashes. The H13 aggregate evidence manifest remains immutable and bound at
127,617 exact receipts.

## Freeze overlap

`production_process_audit.json` was an all-zero, role-neutral process report
whose bytes were reused from development. The old global blob-overlap rule
called this a leak. It is `ROLE_NEUTRAL_CONTENT_REUSE`, not
`FINAL_KNOWLEDGE_LEAK`; source, selector, census, production, oracle, golden and
evaluation roles remain protected.
