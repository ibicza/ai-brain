"""Stage-2 verified skill registry and safe routing API."""

from ai_brain.stage2.models import (
    ConfirmationDecision,
    NextAction,
    QuerySourceKind,
    RetrievalMode,
    SearchStatus,
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
    "NextAction",
    "QuerySourceKind",
    "RetrievalMode",
    "SearchStatus",
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
    "ensure_stage1_compatible",
    "rebuild_from_rule_memory",
]
