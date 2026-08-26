# M-27 Tool Security

Tool execution revalidates request hash, route hash, target, argument hash, ToolRegistry hash, descriptor version, implementation hash, and confirmation hash. A confirmation is valid only for one exact proposal.

Decimal arithmetic forbids `eval`, NaN, infinity, division by zero, unbounded operands, and oversized results. Date parsing accepts ISO dates only. Tools cannot call other tools, access the network, invoke a skill, install a rule, or write FactMemory. Tool results are informational and contain no approval or dispatch fields.
