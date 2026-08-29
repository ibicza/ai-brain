# Capability authority boundary

A capability cannot execute itself. TOOL and SKILL providers remain governed by
ToolRegistry and SkillRegistry. Parser, verifier, solver, renderer, compiler, and
adapter providers are exact contracts pinned by implementation SHA-256. A changed
provider invalidates registry verification and resolution receipts.

Authority classes are DESCRIPTIVE_ONLY, READ_ONLY_EXACT, CONFIRMATION_REQUIRED,
OFFLINE_COMPILATION_ONLY, and ASSISTIVE_ONLY. Packs cannot weaken confirmation,
move offline compilation into user runtime, or let assistive providers grade,
execute, or write memory. Runtime network access is absent.
