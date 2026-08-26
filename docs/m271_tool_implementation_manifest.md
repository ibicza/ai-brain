# M-27.1 Tool Implementation Manifest

`ToolImplementationManifest` replaces entry-function-only hashing. A manifest
binds the entry source, an explicit helper list, constant values, input
normalization, numeric context, output canonicalization, runtime contract and
implementation policy version.

The decimal tool binds parsing and rendering helpers, `DecimalToolLimits`,
operand/digit limits, Decimal context/traps and canonical rendering. The date
tool binds strict ISO parsing, modes and output policy. `ToolDescriptor`,
proposal, confirmation, result and dependency snapshot carry the same manifest
hash. The current manifest is recomputed before confirmation/execution; a stale
helper or constant invalidates authority.

This is an explicit dependency policy. It does not claim to hash arbitrary
dynamic Python behavior, imported runtime internals or the operating system.

