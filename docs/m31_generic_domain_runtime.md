# Generic Domain Runtime

`DomainRuntime` exposes domain/pack identity, concept graph, exercise families,
family-to-concept mapping, operation capabilities, catalog candidates, fact
schemas, adapters, currentness, and a public summary. `GenericDomainRuntime`
implements it using only verified pack data and injected adapters.

Education opens an exact approved installed pack. Conversation and progress use
the same runtime mappings, so no generic file contains chemistry imports,
`if domain == chemistry`, element tables, formula constants, or subject labels
that change execution semantics. Hot lookups use immutable indexes rather than a
full registry verification per request.
