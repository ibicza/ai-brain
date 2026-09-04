# M-33.6 diagnostic authority scope

The frozen diagnostic scope enum is
`DECLARATION_HEADER_BLOCKING`, `ENCLOSING_TYPE_BLOCKING`, `BODY_ONLY`,
`AMBIENT_FILE`, `UNRELATED_DECLARATION`, and `UNKNOWN_SCOPE`.

Only the two explicit blocking scopes can justify withholding a declaration.
`BODY_ONLY` may coexist with a trusted API-header proposal and is reported
separately. `UNKNOWN_SCOPE` never authorizes trust. Final metrics count all scopes,
target associations, and trusted rows; trusted declaration-header diagnostics must
be zero.
