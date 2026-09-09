# M-33.6j.3 graph impact map

The project-local code-review graph was rebuilt at exact Q25 before broad source
reading. `status`, `detect-changes`, `search`, `callers_of`, `callees_of`,
`tests_for`, and `impact --depth 2` were used, then every result was checked in
source and tests.

The active repair path is:

```text
typed JSON authorization input
  -> M336J V2 authorization and freeze manifest
  -> F26 prospective-tree builder
  -> exact Git-object acquisition preflight
  -> inherited acquisition/selection/production engines
  -> V2 evaluator reservation before goldens
  -> source-free H26 publisher
  -> evidence-only E26 publisher
```

The direct blast radius is `scripts/m336j_build_f26.py`,
`scripts/m336i_java_final_route.py`, `m336i_acquisition.py`,
`m336i_evaluation.py`, the V2 authorization/freeze/lineage module, the V2
evaluator ledger, and the H26/E26 publication contract. Indirect consumers are
the M336F selector, Windows/Karina production, sealed replay, public staging,
source-leak verification, and final route-state ledger.

Legacy F24/F25 authority remains available only to historical routes. The V2
path supplies an exact Git executable, derives lineage from Git objects, and
loads one typed freeze manifest shared by builder, controller, provider, and
publishers.
