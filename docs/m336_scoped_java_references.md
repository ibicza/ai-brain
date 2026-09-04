# M-33.6 scoped Java references

The authoritative external reference form is:

`java:<release>/<module>@<source-scope>/<binary-owner>#<member>(<descriptor>)`

The source scope is content-derived for unnamed modules and remains present for
named modules, so the same binary receiver and descriptor in independent roots or
packs do not collide. Human-friendly receiver/method forms are search aliases only
and may correctly return `AMBIGUOUS_OVERLOAD`.

Tests cover identical package/class names in independent roots, identical binary
names in named modules, exact scoped queries, ambiguous short queries, and mutations
of module and source scope.
