# M-22.3a Balanced Benchmark Report

## Distribution

- heldout templates: `200`
- candidate pool: `10000` alpha-unique programs
- unique hidden program templates: `6` / `200` tasks
- unique public specifications: `6`
- clause counts: `{'1': 50, '2': 50, '3': 50, '4': 50}`
- families: `{'drop': 25, 'halt_only': 50, 'phase_switch': 25, 'three_phase_transfer': 50, 'transfer': 25, 'transfer_drop': 25}`
- maximum family fraction: `0.2500`
- public forbidden-key hits: `{'action_count': 0, 'clause_count': 0, 'family': 0, 'fingerprint': 0, 'formal_examples': 0, 'program': 0, 'semantic_hash': 0, 'target': 0}`

## DSL Limitation

The total one-clause DSL admits only unconditional HALT; this bucket contains distinct opaque tasks over that single semantic template.
