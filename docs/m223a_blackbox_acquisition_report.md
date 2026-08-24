# M-22.3a Independent Black-Box Acquisition Validation

## Checks

- local and karina gates: `local passed (338 tests); karina eb7efcf passed (338 tests + 3 runtime-device tests, RTX 5060 8151 MiB)`
- commit at run time: `f653759`
- physical process separation: `True`

## Acquisition

| templates | unique_templates | pool | property_success | hidden_semantic_correct | false_selection | mean_candidates | mean_property_checks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | 6 | 10000 | 1.0000 | 1.0000 | 0.0000 | 3.5000 | 3.5000 |

## Demo-Only Safety

- false selected programs: `0.0000`
- identification may remain low; ambiguity is safe: `{'ambiguity_correct': 0.0, 'false_selected_program': 0.0, 'query_count': 1.2, 'semantic_correct': 1.0}`

## Mutation and Memory

- known-incorrect false accepts: `0` / `10000` known-incorrect (`11014` total mutations)
- reload retention: `1.0000`
- sequential 100 retention: `1.0000`
- silent wrong-rule rate: `0.0000`

## Decision

**OUTCOME B**
