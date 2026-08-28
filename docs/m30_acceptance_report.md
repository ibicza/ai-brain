# M-30 acceptance report

The acceptance command executes 5,000 balanced controlled RU/EN scenarios and
50,000 parsed, action-checked and transition-checked turns, including 1,000
ten-turn scripts. It also runs 10,000 deterministic progress sequences, 2,000
recommendation states, every forbidden state transition, 12 concrete
pending-action fail-closed cases, 1,000 injection strings and the Phase-0
replay/anchor/plan/public mutation batteries. Counters are computed from the
executed checks; failure counters are not declared constants. Machine-readable
local and Karina results are exact-H9 release evidence.
