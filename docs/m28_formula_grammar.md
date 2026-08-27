# M-28 Formula Grammar

Grammar version `1.0` supports exact-case element symbols, positive integer subscripts, parentheses, and nesting to depth 4. It consumes the complete input and produces an immutable AST, canonical rendering, sorted composition, and hashes.

It does not support charges, hydrates/dots, isotopes, square brackets, coefficients, arrows, fractional/negative/zero subscripts, whitespace, or Unicode subscripts. `H2O2` is never reduced to `HO`.

Limits: 256 input characters, 64 groups, 128 element terms, 32 distinct elements, subscript 1,000,000, 10,000,000 total atoms, and 512 canonical output characters.
