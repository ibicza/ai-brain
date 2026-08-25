# M-24.1 Execution Limits

Trusted defaults are `max_register_value=1,000,000`, `max_total_units=1,000,000`, `max_execution_steps=1,000,008`, `max_trace_actions=10,000`, trace disabled, and trace truncation rather than failure. Limits policy version is `1`.

Compiled hard ceilings are 10,000,000 per register, 10,000,000 total units, 10,000,008 steps, and 100,000 captured actions. Callers may lower defaults or raise them only within these ceilings. Integers exclude booleans; negative values, floats, strings, missing/extra registers, invalid policies, and limits over a ceiling fail before execution.

Execution hashes every action incrementally. With trace disabled, no action list grows with the input. With trace enabled, capture stops at the configured bound and reports truncation, or fails before executing the next uncapturable action when `fail_on_trace_overflow` is enabled.
