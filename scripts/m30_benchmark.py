"""Run the complete M-30 controlled conversation and progress CPU benchmark."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ai_brain.stage2.conversation.benchmark import (
    benchmark_pending_actions,
    benchmark_state_transition,
    benchmark_turn_parsing,
    measure_operations,
)
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.models import ExerciseFamily
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.progress.events import make_progress_event
from ai_brain.stage2.progress.models import ProgressEventKind
from ai_brain.stage2.progress.persistence import LearnerProgressStore
from ai_brain.stage2.progress.projection import project_progress
from ai_brain.stage2.progress.recommendations import recommend_exercise

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY = ROOT / "artifacts/domains/chemistry/m29"
CATALOG = ROOT / "artifacts/education/m30/catalog_v4.json"


def _event(index: int, *, learner_id: str = "benchmark"):
    return make_progress_event(
        learner_id=learner_id,
        conversation_id=f"conversation-{index}",
        tutor_session_id=f"session-{index}",
        catalog_entry_hash="catalog",
        semantic_key_hash=f"key-{index}",
        concept_ids=("FORMULA_PARSING",),
        event_kind=ProgressEventKind.ANSWER_GRADED,
        sequence=1,
        previous_event_hash=None,
        grading_result_hash=f"grade-{index}",
        correct=True,
        observed_at="2026-01-01T00:00:00Z",
    )


def progress_benchmarks(root: Path, count: int = 10_000):
    store = LearnerProgressStore.initialize(root / "progress")
    append_count = 1_000
    events = tuple(
        _event(index, learner_id=f"append-{index}") for index in range(append_count)
    )
    append = measure_operations(append_count, lambda index: store.append(events[index]))
    projection_events = tuple(_event(index) for index in range(count))
    projection = measure_operations(
        count, lambda index: project_progress("benchmark", (projection_events[index],))
    )
    empty = project_progress("recommendation", ())
    candidates = {"ELEMENT_IDENTITY": (("entry", "semantic"),)}
    recommendation = measure_operations(
        count,
        lambda _index: recommend_exercise(
            "recommendation",
            empty,
            candidates,
            generated_at="2026-01-01T00:00:00Z",
        ),
    )
    backup = measure_operations(
        1, lambda _index: store.backup(root / "progress-backup.sqlite3")
    )
    return {
        "progress_event_append": append,
        "progress_projection": projection,
        "recommendation": recommendation,
        "structural_backup": backup,
    }


def educational_benchmarks(root: Path, samples: int = 20):
    chemistry_root = root / "chemistry"
    shutil.copytree(CHEMISTRY, chemistry_root)
    service = EducationalService.open(
        chemistry_root, root / "education", catalog_path=CATALOG
    )
    created_at = "2026-01-01T00:00:00Z"
    presentation = measure_operations(
        samples,
        lambda index: service.create_exercise(
            ExerciseFamily.MOLAR_MASS_SIMPLE,
            seed=index,
            language=("ru", "en")[index % 2],
            session_id=f"presentation-{index}",
            created_at=created_at,
        ),
    )

    def prepare(prefix: str, *, submit: bool = False):
        identities = []
        for index in range(samples):
            identity = f"{prefix}-{index}"
            service.create_exercise(
                ExerciseFamily.MOLAR_MASS_SIMPLE,
                seed=1_000 + index,
                language="en",
                session_id=identity,
                created_at=created_at,
            )
            if submit:
                service.submit_answer(identity, "0 g/mol", created_at=created_at)
            identities.append(identity)
        return tuple(identities)

    submission_ids = prepare("submission")
    answer_submission = measure_operations(
        samples,
        lambda index: service.submit_answer(
            submission_ids[index], "0 g/mol", created_at=created_at
        ),
    )
    hint_ids = prepare("hint")
    hint = measure_operations(samples, lambda index: service.hint(hint_ids[index]))
    solution_ids = prepare("solution", submit=True)
    solution = measure_operations(
        samples, lambda index: service.show_solution(solution_ids[index])
    )

    entry = next(
        item
        for item in service.catalog.entries
        if item.exercise_spec.family is ExerciseFamily.MOLAR_MASS_SIMPLE
    )
    expected = entry.internal_instance.hidden_expected_answer
    parsed = parse_student_answer(
        f"{expected['value']} {expected['unit']}",
        entry.exercise_spec.accepted_answer_type,
        supported_symbols=set(service.chemistry.manifest["supported_elements"]),
        confirmed=True,
    )
    grading = measure_operations(
        100,
        lambda index: grade_answer(
            entry.internal_instance,
            parsed,
            entry.graph,
            attempt_id=f"benchmark-grade-{index}",
            created_at=created_at,
        ),
    )
    replay_id = solution_ids[0]
    replay = measure_operations(10, lambda _index: service.replay(replay_id))
    authority = measure_operations(1, lambda _index: service.verify())
    if service.execution_monitor.count:
        raise RuntimeError("M-30 runtime benchmark executed a chemistry tool")
    return {
        "exercise_presentation": presentation,
        "answer_submission": answer_submission,
        "grading": grading,
        "hint": hint,
        "solution": solution,
        "replay": replay,
        "authority_verification": authority,
        "runtime_chemistry_executions": 0,
        "educational_samples_per_mutating_stage": samples,
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="m30-benchmark-") as directory:
        root = Path(directory)
        result = {
            "status": "PASS",
            "mixed_conversation_turn_count": 10_000,
            "conversation_turn_parse": benchmark_turn_parsing(),
            "conversation_state_transition": benchmark_state_transition(),
            **benchmark_pending_actions(),
            **progress_benchmarks(root),
            **educational_benchmarks(root),
        }
    print(canonical_json(result))


if __name__ == "__main__":
    main()
