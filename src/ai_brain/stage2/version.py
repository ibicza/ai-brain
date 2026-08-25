"""Stage-2 registry contract and frozen Stage-1 dependency guard."""

from ai_brain.stage1.version import STAGE1_VERSION

STAGE2_SCHEMA_VERSION = 1
SKILL_REGISTRY_SCHEMA_VERSION = 1
EXPECTED_STAGE1_VERSION = "1.0.1"
EXPECTED_STAGE1_RELEASE_COMMIT = "4e9520a16bd3aeb7579ea92ce44060fd7f1a705a"


class IncompatibleStage1Error(RuntimeError):
    """The imported trusted Stage-1 contract is not the frozen release."""


def ensure_stage1_compatible() -> None:
    if STAGE1_VERSION != EXPECTED_STAGE1_VERSION:
        raise IncompatibleStage1Error(
            f"Stage-2 requires Stage-1 {EXPECTED_STAGE1_VERSION}, got {STAGE1_VERSION}"
        )
