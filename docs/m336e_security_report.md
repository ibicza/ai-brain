# M-33.6e security report

M-33.6e preserves the frozen authority and SPDX security properties from
M-33.6d: zero accepted authority forgeries, widening receipts, cross-source
replays, and cross-run replays; exact JDK reference isolation; zero false
automatic license identities; zero accepted substantive mutations; correct AND,
OR, WITH, scoped-license, and SCM-correspondence behavior; and exact H17 field
mapping.

New regressions cover canonical path traversal, drive paths, separator variants,
NFC and casefold collisions, manifest mutation, persistent-ledger mutation and
restart, infeasible zero-invocation selection, registry deletion/replacement/
reordering/parent-skip, typed producer drift, nested unknown fields, and encoded
source leaks. Final security evidence must report PASS and retain at least 10,260
rejected adaptive mutations with zero accepted.
