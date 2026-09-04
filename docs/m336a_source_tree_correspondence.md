# Source tree correspondence

Archive and repository paths are NFC-normalized and traversal-safe. Every Java entry records raw and canonical SHA-256. Matching is restricted to a frozen module source root; same-path/suffix canonical equality is `EXACT_MATCH`, a unique other path is `PATH_RELOCATED_EXACT_CONTENT`, no match is `UNMATCHED`, and multiple matches are `AMBIGUOUS_MATCH`. Generated evidence is a distinct explicit status and is never inferred.

Disclosed results: Guava 615 exact, Commons 359 exact, Caffeine 50 exact; relocated, unmatched, ambiguous, and generated counts are all zero. External license closure accepts only exact, relocated-exact, or separately verified generated entries.
