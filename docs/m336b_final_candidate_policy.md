# M-33.6b final candidate metadata policy

The frozen OPTIONAL pool contains six independent families: Jackson Databind 2.20.0, Log4j API 2.25.2, Reactor Core 3.7.9, picocli 4.7.7, HttpCore5 5.3.6, and Gson 2.13.2. The policy binds exact Maven coordinates, expected GitHub repositories and tag refs, source prefixes, Java 21 compatibility, POM hashes learned from allowed metadata GETs, source lengths learned from HEAD, and checksum/signature availability.

No source archive body, SCM archive body, Java body, ZIP listing, callable census, parser result, source hash, semantic result, or trust result is frozen. Candidate order is the declared tuple. No failed candidate is replaced.

Global minima require at least two distinct eligible roots. Selection is a single deterministic per-family round robin keyed by exact F17 SHA, over the exact sorted eligible roots, with the published census/diversity limits and full accumulated denylist.
