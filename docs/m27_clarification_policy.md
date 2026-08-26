# M-27 Clarification Policy

Clarification is typed and asks for one exact missing field. Supported classes cover fact/skill/tool target ambiguity, ambiguous entities, unknown predicates, missing skill destinations, missing tool arguments, multi-intent input, and unsupported operations.

Russian and English questions are stored together. Only one clarification round is permitted. A second ambiguous result remains `AMBIGUOUS_ROUTE` with `CLARIFICATION_LIMIT_REACHED`; it is not auto-selected. Composite requests are not clarified into a hidden plan and must be split manually.
