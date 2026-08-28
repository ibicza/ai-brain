# M-30 conversation state machine

States are `IDLE`, `EXERCISE_ACTIVE`, `AWAITING_CONFIRMATION`, `AWAITING_CLARIFICATION`, `PAUSED`, and terminal `CLOSED`. Confirmation, clarification and pause retain the previous active state. Answer, hint and solution require an active exercise; paused and closed states reject unauthorized actions. Each turn authorizes at most one transition and one trusted action.
