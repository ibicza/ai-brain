# M-27 Tool Registry

ToolRegistry is independent of FactMemory, SkillRegistry, and RuleMemory. Descriptor and registry hashes bind names, aliases, typed schemas, execution class, policy, version, and implementation source hash.

M-27 installs two tools:

- `decimal_arithmetic`: exact `Decimal` ADD, SUBTRACT, MULTIPLY, and DIVIDE with operand/count/digit limits.
- `date_difference`: two ISO dates with explicit `SIGNED` or `ABSOLUTE` mode.

Both are deterministic `PURE_LOCAL_READ_ONLY` tools. Every call still requires explicit confirmation. External, networked, side-effecting, unknown, and arbitrary-code tools fail closed.
