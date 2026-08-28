# M-30 pending-action security

Pending IDs use opaque random tokens. Stored actions bind learner, conversation, language, request, action payload, prior state, expiry and catalog/domain/FactMemory/source/tool dependencies. Guessing, context substitution, expiry, cancellation, repeated use or dependency drift fails before execution. Normal preparation performs no tool execution.
