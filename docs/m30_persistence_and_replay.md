# M-30 persistence and replay

Conversation and progress use separate SQLite databases with explicit schemas, foreign keys, busy timeouts, canonical payload checksums, append-only chains and atomic updates. Both support verify, backup and restore without silent migration. Replay reconstructs conversation state, turn/public-response chains, pending state and progress, while reporting historical integrity separately from current educational authority.
