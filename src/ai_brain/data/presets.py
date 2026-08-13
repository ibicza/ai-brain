from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_brain.data.generators import GeneratorName


@dataclass(frozen=True)
class TaskPreset:
    name: str
    task_types: tuple[GeneratorName, ...]
    description: str
    default_profile: str = "train"
    default_train_profile: str = "train"
    default_eval_profile: str = "eval"


TASK_PRESETS: dict[str, TaskPreset] = {
    "arithmetic": TaskPreset(
        name="arithmetic",
        task_types=(
            "arithmetic.add",
            "arithmetic.subtract",
            "arithmetic.missing_addend",
            "arithmetic.double_step",
            "arithmetic.compare_sum",
        ),
        description="Arithmetic reasoning tasks.",
    ),
    "quantity_direct": TaskPreset(
        name="quantity_direct",
        task_types=(
            "quantity.direct",
            "quantity.location_direct",
            "quantity.known_zero",
        ),
        description="Direct quantity lookup tasks.",
    ),
    "sorting_short": TaskPreset(
        name="sorting_short",
        task_types=(
            "sorting.ascending",
            "sorting.descending",
        ),
        description="Short sorting tasks with 3-4 numbers.",
        default_profile="train_short",
        default_train_profile="train_short",
        default_eval_profile="eval_short",
    ),
    "state_change": TaskPreset(
        name="state_change",
        task_types=(
            "state_change.add",
            "state_change.subtract",
            "state_change.other_subject_no_change",
            "state_change.other_object_no_change",
            "state_change.insufficient_start",
        ),
        description="State transition reasoning tasks.",
    ),
}

TASK_PRESET_NAMES: tuple[str, ...] = tuple(sorted(TASK_PRESETS))


def available_task_presets() -> tuple[str, ...]:
    return TASK_PRESET_NAMES


def get_task_preset(name: str) -> TaskPreset:
    try:
        return TASK_PRESETS[name]
    except KeyError as error:
        available = ", ".join(available_task_presets())
        raise ValueError(
            f"Unknown task preset: {name}. Available presets: {available}"
        ) from error


def resolve_task_selection(
    *,
    task_preset: str | None,
    task_types: Sequence[GeneratorName] | None,
) -> tuple[list[GeneratorName] | None, str | None]:
    if task_preset and task_types:
        raise ValueError("Cannot use --task-preset together with --task-type.")

    if not task_preset:
        return list(task_types) if task_types is not None else None, None

    preset = get_task_preset(task_preset)
    return list(preset.task_types), preset.name
