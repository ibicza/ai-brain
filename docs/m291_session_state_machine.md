# M-29.1 session state machine

`sessions.py::ALLOWED_EVENT_STATES` explicitly governs PRESENTED, ATTEMPTED, HINTED, SOLVED, SOLUTION_REVEALED and ABANDONED.

Answers, grades, hints, solution and abandonment are accepted only from declared states. Grades must follow an ungraded attempt. Terminal states reject mutation; SOLVED permits only solution reveal. Duplicate solution, invalid sequence, bad previous hash and state regression fail.

Every event hash binds its session, sequence, type, payload, previous event and timestamp. Store verification reconstructs the event chain and enforces referenced student-answer, grading, hint and explanation artifacts. The acceptance matrix covers all 30 state/event pairs with zero invalid transitions accepted and zero valid transitions rejected.
