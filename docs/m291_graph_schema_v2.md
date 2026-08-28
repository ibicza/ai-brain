# M-29.1 derivation graph schema v2

Graph v2 binds the complete source-result artifact, source-result hash, domain and knowledge snapshots, source chain, tool implementation, calculation and rounding policies, provenance sets, typed nodes, edges and root.

For every operation node, input arity equals `exact_inputs` arity and each ordered `exact_inputs[i]` equals the canonical typed output of `input_node_ids[i]`. Every input must also have a graph edge. Duplicate, missing, reordered, copied and representation-shifted inputs fail.

Dimensions are a closed `EducationalDimension` enum. Source provenance on the graph and nodes must be an exact subset/binding of the complete source artifact. The v2 mutation battery rehashes tampered nodes and containers so rejection cannot rely on a stale outer checksum.
