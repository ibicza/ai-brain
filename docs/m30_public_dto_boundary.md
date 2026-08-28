# M-30 public DTO boundary

Conversation responses expose state, language, learner-facing text and at most one public education payload, progress summary, opaque prepared action or clarification. Graphs, hidden answers, receipts, source results, FactMemory identifiers, internal pending records and event hashes are forbidden and checked before persistence/printing.
