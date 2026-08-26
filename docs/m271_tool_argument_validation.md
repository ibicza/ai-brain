# M-27.1 Tool Argument Validation

`ToolRegistry.validate_and_canonicalize_arguments` owns exact per-tool schemas.
Unknown or missing keys are rejected. Decimal operations use an exact enum,
bounded operands and canonical decimal strings. Date differences require exactly
`start_date`, `end_date` and `mode`, canonical ISO dates and a supported mode.

Only a successful validation returns canonical arguments and `argument_hash`.
Exact routing requires that result. Invalid calls receive `INVALID_REQUEST`, no
proposal and no confirmation request. Preparation and execution revalidate the
arguments and current implementation manifest.

Expected failures append bounded audit records such as
`TOOL_ARGUMENT_INVALID`, `TOOL_RESOURCE_LIMIT_REJECTED`,
`TOOL_IMPLEMENTATION_STALE` and `TOOL_EXECUTION_FAILED`; raw hostile operands are
not copied into audit payloads.

