# Javadoc-like extraction

Static Javadoc-like HTML is sanitized before extraction. Explicit `@api` records capture receiver, method, parameters, return type, represented generic constraints, preconditions, postconditions, declared exceptions, deprecation metadata, and examples. `@test` records remain distinct `TEST_CASE` content.

Source code and examples are descriptive bytes only. M-32 does not compile or execute them. The fixture is a bounded documentation grammar, not complete Java parsing.
