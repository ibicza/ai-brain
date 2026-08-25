"""Stage-2 verified skill registry and safe routing API."""

from ai_brain.stage2.models import (
    ConfirmationDecision,
    EquivalenceScope,
    FinalStateEquivalenceGroup,
    NextAction,
    QuerySourceKind,
    RetrievalMode,
    SearchStatus,
    SemanticEquivalenceGroup,
    SkillCandidate,
    SkillDispatchReceipt,
    SkillQuery,
    SkillRecord,
    SkillRegistryManifest,
    SkillSearchResult,
    SkillSelectionReceipt,
)
from ai_brain.stage2.registry import (
    SkillRegistry,
    SkillRegistryIntegrityError,
    SkillRegistryStaleError,
    rebuild_from_rule_memory,
)
from ai_brain.stage2.semantics import (
    build_equivalence_groups,
    build_final_state_equivalence_groups,
    final_state_effect_hash,
    final_state_effect_signature,
    semantic_effect_hash,
    semantic_effect_signature,
)
from ai_brain.stage2.service import (
    ConfirmationRequiredError,
    SkillDispatchError,
    Stage2Router,
)
from ai_brain.stage2.version import STAGE2_SCHEMA_VERSION, ensure_stage1_compatible

ensure_stage1_compatible()

__all__ = [
    "STAGE2_SCHEMA_VERSION",
    "ConfirmationDecision",
    "ConfirmationRequiredError",
    "EquivalenceScope",
    "FinalStateEquivalenceGroup",
    "NextAction",
    "QuerySourceKind",
    "RetrievalMode",
    "SearchStatus",
    "SemanticEquivalenceGroup",
    "SkillCandidate",
    "SkillDispatchError",
    "SkillDispatchReceipt",
    "SkillQuery",
    "SkillRecord",
    "SkillRegistry",
    "SkillRegistryIntegrityError",
    "SkillRegistryManifest",
    "SkillRegistryStaleError",
    "SkillSearchResult",
    "SkillSelectionReceipt",
    "Stage2Router",
    "build_equivalence_groups",
    "build_final_state_equivalence_groups",
    "ensure_stage1_compatible",
    "final_state_effect_hash",
    "final_state_effect_signature",
    "rebuild_from_rule_memory",
    "semantic_effect_hash",
    "semantic_effect_signature",
]
