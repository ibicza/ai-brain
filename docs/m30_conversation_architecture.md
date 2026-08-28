# M-30 conversation architecture

The conversational service is a bounded orchestrator over the trusted educational service and a separate observable progress store. Controlled parsing selects one intent, the state machine authorizes one action, the education layer produces the only authority-bearing payload, and a checksummed turn records only input and public-response hashes. No network, model checkpoint or training import is used.
