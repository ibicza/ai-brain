"""Answer receipt validation helpers."""

from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import FactAnswerBundle, ReplayStatus


def validate_answer_replay(
    memory: FactMemory, bundle: FactAnswerBundle
) -> ReplayStatus:
    return memory.replay_answer(bundle)
