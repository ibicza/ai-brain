# M-33.6f exact field evidence

R20 had one wrong generic-constraint row out of 66,943. The extractor incorrectly selected enclosing-type variables for a method-owned bound. The repair selects callable-owned type variables for callable evidence and is covered by generic, neighboring, nested and negative tests.

Production and evaluator compute rows independently from a shared versioned specification. Each conformance row binds proposal, declaration, field, canonical value hash, node/span evidence hashes, resolver manifest, policy, production evidence and row hash.

The 180-file development evaluation has 59,864 required/present/exact rows and missing/extra/duplicate/wrong counts `0/0/0/0`; completeness and exactness are `1.000000`. The conformance report hash is `70aa3b58952583d9fe3afc4c29e1243ef1283634c2ef3133e5e8a03d8b3930d7`.
