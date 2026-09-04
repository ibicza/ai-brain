# M-33.6b schema-bound disclosure

The H17 role manifest binds every added H17 path to a closed role. Protected roles cover source and acquisition bytes, provenance receipts, selector output, census, production output, candidate pack, oracle, goldens, evaluation, approval, installation, and final decision.

Claim extraction is role- and field-path-specific. Source files derive their actual Git path plus raw and canonical hashes. Receipts derive archive/POM/source/tree/SCM identities. Selector output derives every selected path and source hash. Production, oracle, golden, evaluation, approval, installation, and decision roles expose only their mandatory typed claims.

Each role report records required, extracted, missing, and extra counts. Any protected role with a missing mandatory claim or unexpected protected field fails; absent field traversal cannot silently satisfy the denominator.
