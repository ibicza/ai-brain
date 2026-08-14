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
    "digit_table": TaskPreset(
        name="digit_table",
        task_types=(
            "arithmetic.digit_add_no_carry",
            "arithmetic.digit_add_with_carry_input",
            "arithmetic.digit_add_carry_out",
            "arithmetic.digit_sub_no_borrow",
            "arithmetic.digit_sub_with_borrow_input",
            "arithmetic.digit_sub_borrow_out",
        ),
        description="Full digit addition/subtraction table with carry and borrow.",
    ),
    "digit_table_composition": TaskPreset(
        name="digit_table_composition",
        task_types=(
            "arithmetic.add_2digit_composed",
            "arithmetic.sub_2digit_composed",
        ),
        description="Two-digit add/sub composition using compact digit traces.",
    ),
    "digit_add_carry": TaskPreset(
        name="digit_add_carry",
        task_types=("arithmetic.digit_add_carry",),
        description="Single digit addition with incoming carry.",
    ),
    "digit_sub_borrow": TaskPreset(
        name="digit_sub_borrow",
        task_types=("arithmetic.digit_sub_borrow",),
        description="Single digit subtraction with incoming borrow.",
    ),
    "add_2digit_no_carry": TaskPreset(
        name="add_2digit_no_carry",
        task_types=("arithmetic.add_2digit_no_carry",),
        description="Two-digit addition without carry.",
    ),
    "add_2digit_with_carry": TaskPreset(
        name="add_2digit_with_carry",
        task_types=("arithmetic.add_2digit_with_carry",),
        description="Two-digit addition with carry.",
    ),
    "sub_2digit_no_borrow": TaskPreset(
        name="sub_2digit_no_borrow",
        task_types=("arithmetic.sub_2digit_no_borrow",),
        description="Two-digit subtraction without borrow.",
    ),
    "sub_2digit_with_borrow": TaskPreset(
        name="sub_2digit_with_borrow",
        task_types=("arithmetic.sub_2digit_with_borrow",),
        description="Two-digit subtraction with borrow.",
    ),
    "missing_addend_simple": TaskPreset(
        name="missing_addend_simple",
        task_types=("arithmetic.missing_addend_simple",),
        description="Missing addend represented as target minus known.",
    ),
    "compare_sum_simple": TaskPreset(
        name="compare_sum_simple",
        task_types=("arithmetic.compare_sum_simple",),
        description="Compute and compare two sums.",
    ),
    "double_step_simple": TaskPreset(
        name="double_step_simple",
        task_types=("arithmetic.double_step_simple",),
        description="Add then subtract with simple subset labels.",
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
