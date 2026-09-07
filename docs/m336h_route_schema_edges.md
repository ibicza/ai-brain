# M-33.6h route schema edges

The route manifest derives 42 dependency edges and 42 typed schema edges from registry bindings. An edge is executable only when both callables resolve and the producer response schema hash exactly equals the consumer's required request schema hash.

Preflight rejects unresolved components, ambiguous components, uncontracted edges, incompatible route edges, incompatible schema edges, forbidden cycles, a selector route/algorithm identity collision, legacy-selector reachability, disclosed-wrapper reachability, or a changed source/signature/schema identity.

The full edge denominator and row hashes are part of the exact-R23 route manifest and Q23 evidence.
