from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from ai_brain.data.schema import TrainingExample
from ai_brain.data.templates import (
    CATEGORY_RULES,
    COLORS,
    COUNTED_NOUNS,
    LOCATIONS,
    OBJECT_PROPERTIES,
    PEOPLE,
    CountedNoun,
    Location,
    Person,
    choose_past_be_verb,
    format_counted_noun,
    format_counted_noun_accusative,
)

GeneratorName = str
GenerationProfileName = Literal["train", "eval", "train_short", "eval_short"]


@dataclass(frozen=True)
class GenerationProfile:
    name: GenerationProfileName

    def randint(self, rng: random.Random, low: int, high: int) -> int:
        if self.name in {"train_short", "eval_short"} and (low, high) == (3, 5):
            return rng.randint(3, 4)

        train_ranges = {
            (0, 30): (0, 50),
            (0, 20): (0, 30),
            (0, 10): (0, 20),
            (1, 20): (1, 30),
            (1, 10): (1, 15),
        }
        if self.name in {"train", "train_short"}:
            train_low, train_high = train_ranges.get((low, high), (low, high))
            return rng.randint(train_low, train_high)

        eval_ranges = {
            (0, 99): (20, 199),
            (0, 30): (20, 100),
            (0, 20): (20, 80),
            (0, 10): (20, 60),
            (1, 20): (21, 100),
            (1, 10): (11, 40),
            (3, 5): (5, 8),
            (0, 9999): (10_000, 99_999),
        }
        eval_low, eval_high = eval_ranges.get((low, high), (low, high))
        return rng.randint(eval_low, eval_high)

    def sample_range(self, rng: random.Random, stop: int, count: int) -> list[int]:
        if self.name in {"train", "train_short"}:
            return rng.sample(range(stop), count)

        if stop == 100:
            return rng.sample(range(20, 200), count)

        if stop == 50:
            return rng.sample(range(20, 120), count)

        return rng.sample(range(stop), count)


TRAIN_PROFILE = GenerationProfile(name="train")
EVAL_PROFILE = GenerationProfile(name="eval")
TRAIN_SHORT_PROFILE = GenerationProfile(name="train_short")
EVAL_SHORT_PROFILE = GenerationProfile(name="eval_short")
GENERATION_PROFILES: dict[GenerationProfileName, GenerationProfile] = {
    "train": TRAIN_PROFILE,
    "eval": EVAL_PROFILE,
    "train_short": TRAIN_SHORT_PROFILE,
    "eval_short": EVAL_SHORT_PROFILE,
}


def resolve_generation_profile(
    profile: GenerationProfileName | GenerationProfile,
) -> GenerationProfile:
    if isinstance(profile, GenerationProfile):
        return profile

    try:
        return GENERATION_PROFILES[profile]
    except KeyError as error:
        raise ValueError(f"Unknown generation profile: {profile}") from error


GeneratorFunction = Callable[[random.Random, int, GenerationProfile], TrainingExample]


def _pick_distinct_people(rng: random.Random, count: int) -> list[Person]:
    return rng.sample(PEOPLE, count)


def _pick_distinct_nouns(rng: random.Random, count: int) -> list[CountedNoun]:
    return rng.sample(COUNTED_NOUNS, count)


def _pick_distinct_locations(rng: random.Random, count: int) -> list[Location]:
    return rng.sample(LOCATIONS, count)


def _make_quantity_fact(
    subject: Person, noun: CountedNoun, count: int
) -> tuple[str, str]:
    counted_noun = format_counted_noun(count, noun)
    be_verb = choose_past_be_verb(count, noun)
    fact = f"У {subject.genitive} {be_verb} {counted_noun}."
    return fact, be_verb


def _make_location_quantity_fact(
    location: Location,
    noun: CountedNoun,
    count: int,
) -> tuple[str, str]:
    counted_noun = format_counted_noun(count, noun)
    be_verb = choose_past_be_verb(count, noun)
    fact = f"{location.where.capitalize()} {be_verb} {counted_noun}."
    return fact, be_verb


def _quantity_question(subject: Person, noun: CountedNoun) -> str:
    return f"Сколько {noun.question} было у {subject.genitive}?"


def _location_quantity_question(location: Location, noun: CountedNoun) -> str:
    return f"Сколько {noun.question} было {location.where}?"


def _insufficient_answer(reason: str) -> str:
    return f"Недостаточно информации: {reason}."


def _case_prefix(rng: random.Random, profile: GenerationProfile) -> str:
    return f"case {profile.randint(rng, 0, 9999)}. "


def generate_comparison_max(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 99)
    b = profile.randint(rng, 0, 99)

    while b == a:
        b = profile.randint(rng, 0, 99)

    templates = (
        "Что больше: {a} или {b}?",
        "Выбери большее число: {a} или {b}.",
        "Какое число больше — {a} или {b}?",
        "Сравни {a} и {b}. Напиши большее число.",
    )
    prompt = rng.choice(templates).format(a=a, b=b)

    return TrainingExample(
        id=f"comparison.max:{index:08d}",
        task_type="comparison.max",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(max(a, b)),
        metadata={"a": a, "b": b, "operation": "max"},
    )


def generate_comparison_min(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 99)
    b = profile.randint(rng, 0, 99)

    while b == a:
        b = profile.randint(rng, 0, 99)

    templates = (
        "Что меньше: {a} или {b}?",
        "Выбери меньшее число: {a} или {b}.",
        "Какое число меньше — {a} или {b}?",
        "Сравни {a} и {b}. Напиши меньшее число.",
    )
    prompt = rng.choice(templates).format(a=a, b=b)

    return TrainingExample(
        id=f"comparison.min:{index:08d}",
        task_type="comparison.min",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(min(a, b)),
        metadata={"a": a, "b": b, "operation": "min"},
    )


def generate_comparison_equality(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 30)
    b = a if rng.choice((True, False)) else profile.randint(rng, 0, 30)

    if b != a:
        answer = "Нет."
    else:
        answer = "Да."

    templates = (
        "Числа {a} и {b} равны?",
        "Правда ли, что {a} = {b}?",
        "Сравни числа {a} и {b}. Они одинаковые?",
    )
    prompt = rng.choice(templates).format(a=a, b=b)

    return TrainingExample(
        id=f"comparison.equality:{index:08d}",
        task_type="comparison.equality",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=answer,
        metadata={"a": a, "b": b, "operation": "equality", "equal": a == b},
    )


def generate_comparison_three_max(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    numbers = profile.sample_range(rng, 100, 3)
    joined = ", ".join(str(number) for number in numbers)
    templates = (
        "Какое число самое большое: {joined}?",
        "Выбери максимум из чисел: {joined}.",
        "Найди наибольшее число среди: {joined}.",
    )
    prompt = rng.choice(templates).format(joined=joined)

    return TrainingExample(
        id=f"comparison.three_max:{index:08d}",
        task_type="comparison.three_max",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(max(numbers)),
        metadata={"numbers": numbers, "operation": "three_max"},
    )


def generate_comparison_three_min(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    numbers = profile.sample_range(rng, 100, 3)
    joined = ", ".join(str(number) for number in numbers)
    templates = (
        "Какое число самое маленькое: {joined}?",
        "Выбери минимум из чисел: {joined}.",
        "Найди наименьшее число среди: {joined}.",
    )
    prompt = rng.choice(templates).format(joined=joined)

    return TrainingExample(
        id=f"comparison.three_min:{index:08d}",
        task_type="comparison.three_min",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(min(numbers)),
        metadata={"numbers": numbers, "operation": "three_min"},
    )


def generate_sorting_ascending(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    numbers = profile.sample_range(rng, 50, profile.randint(rng, 3, 5))
    joined = ", ".join(str(number) for number in numbers)
    answer_numbers = sorted(numbers)
    templates = (
        "Отсортируй числа по возрастанию: {joined}.",
        "Запиши числа от меньшего к большему: {joined}.",
        "Упорядочь числа по возрастанию: {joined}.",
    )
    prompt = rng.choice(templates).format(joined=joined)

    return TrainingExample(
        id=f"sorting.ascending:{index:08d}",
        task_type="sorting.ascending",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=", ".join(str(number) for number in answer_numbers),
        metadata={"numbers": numbers, "operation": "sort_ascending"},
    )


def generate_sorting_descending(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    numbers = profile.sample_range(rng, 50, profile.randint(rng, 3, 5))
    joined = ", ".join(str(number) for number in numbers)
    answer_numbers = sorted(numbers, reverse=True)
    templates = (
        "Отсортируй числа по убыванию: {joined}.",
        "Запиши числа от большего к меньшему: {joined}.",
        "Упорядочь числа по убыванию: {joined}.",
    )
    prompt = rng.choice(templates).format(joined=joined)

    return TrainingExample(
        id=f"sorting.descending:{index:08d}",
        task_type="sorting.descending",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=", ".join(str(number) for number in answer_numbers),
        metadata={"numbers": numbers, "operation": "sort_descending"},
    )


def generate_order_before_after(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    people = _pick_distinct_people(rng, 4)
    target_index = rng.randint(1, len(people) - 2)
    target = people[target_index]
    ask_before = rng.choice((True, False))

    joined = ", ".join(person.nominative for person in people)

    if ask_before:
        prompt = f"В очереди стоят: {joined}. Кто стоит перед {target.instrumental}?"
        answer = people[target_index - 1].nominative
        relation = "before"
    else:
        prompt = f"В очереди стоят: {joined}. Кто стоит после {target.genitive}?"
        answer = people[target_index + 1].nominative
        relation = "after"

    return TrainingExample(
        id=f"order.before_after:{index:08d}",
        task_type="order.before_after",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=answer,
        metadata={
            "people": [person.nominative for person in people],
            "target": target.nominative,
            "relation": relation,
        },
    )


def generate_addition(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 20)
    b = profile.randint(rng, 0, 20)
    templates = (
        "Сколько будет {a} + {b}?",
        "К {a} прибавь {b}. Что получится?",
        "Найди сумму чисел {a} и {b}.",
        "Посчитай: {a} плюс {b}.",
    )
    prompt = rng.choice(templates).format(a=a, b=b)

    return TrainingExample(
        id=f"arithmetic.add:{index:08d}",
        task_type="arithmetic.add",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(a + b),
        metadata={"a": a, "b": b, "operation": "addition"},
    )


def generate_subtraction(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 30)
    b = rng.randint(0, a)
    templates = (
        "Сколько будет {a} - {b}?",
        "Из {a} вычти {b}. Что получится?",
        "Найди разность чисел {a} и {b}.",
        "Посчитай: {a} минус {b}.",
    )
    prompt = rng.choice(templates).format(a=a, b=b)

    return TrainingExample(
        id=f"arithmetic.subtract:{index:08d}",
        task_type="arithmetic.subtract",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(a - b),
        metadata={"a": a, "b": b, "operation": "subtraction"},
    )


def generate_missing_addend(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 20)
    missing = profile.randint(rng, 0, 20)
    total = a + missing
    templates = (
        "Какое число надо прибавить к {a}, чтобы получить {total}?",
        "{a} + □ = {total}. Какое число пропущено?",
        "До {total} не хватает сколько, если уже есть {a}?",
    )
    prompt = rng.choice(templates).format(a=a, total=total)

    return TrainingExample(
        id=f"arithmetic.missing_addend:{index:08d}",
        task_type="arithmetic.missing_addend",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(missing),
        metadata={"a": a, "missing": missing, "total": total},
    )


def generate_compare_sum(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 10)
    b = profile.randint(rng, 0, 10)
    c = profile.randint(rng, 0, 10)
    d = profile.randint(rng, 0, 10)
    left = a + b
    right = c + d

    while right == left:
        c = profile.randint(rng, 0, 10)
        d = profile.randint(rng, 0, 10)
        right = c + d

    templates = (
        "Что больше: {a} + {b} или {c} + {d}? Ответь числом.",
        "Сравни суммы {a} + {b} и {c} + {d}. Какая сумма больше?",
        "Найди большее значение: {a} + {b} или {c} + {d}.",
    )
    prompt = rng.choice(templates).format(a=a, b=b, c=c, d=d)

    return TrainingExample(
        id=f"arithmetic.compare_sum:{index:08d}",
        task_type="arithmetic.compare_sum",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(max(left, right)),
        metadata={"left": left, "right": right, "operation": "compare_sum"},
    )


def generate_double_step(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    a = profile.randint(rng, 0, 20)
    b = profile.randint(rng, 0, 10)
    c = rng.randint(0, a + b)
    templates = (
        "К {a} прибавь {b}, потом вычти {c}. Что получится?",
        "Сначала было {a}. Добавили {b}, затем убрали {c}. Сколько осталось?",
        "Посчитай в два шага: {a} + {b} - {c}.",
    )
    prompt = rng.choice(templates).format(a=a, b=b, c=c)

    return TrainingExample(
        id=f"arithmetic.double_step:{index:08d}",
        task_type="arithmetic.double_step",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(a + b - c),
        metadata={"a": a, "b": b, "c": c, "operation": "add_then_subtract"},
    )


def generate_arithmetic_progression(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    start = profile.randint(rng, 0, 20)
    step = profile.randint(rng, 1, 10)
    length = 4
    numbers = [start + step * offset for offset in range(length)]
    answer = start + step * length
    sequence = ", ".join(str(number) for number in numbers)
    templates = (
        "Продолжи последовательность: {sequence}.",
        "Какое число будет следующим: {sequence}?",
        "Найди следующий элемент ряда: {sequence}.",
    )
    prompt = rng.choice(templates).format(sequence=sequence)

    return TrainingExample(
        id=f"sequence.arithmetic_progression:{index:08d}",
        task_type="sequence.arithmetic_progression",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(answer),
        metadata={"start": start, "step": step, "length": length},
    )


def generate_decreasing_progression(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    step = profile.randint(rng, 1, 10)
    start = rng.randint(step * 5, step * 5 + 30)
    length = 4
    numbers = [start - step * offset for offset in range(length)]
    answer = start - step * length
    sequence = ", ".join(str(number) for number in numbers)
    templates = (
        "Продолжи убывающую последовательность: {sequence}.",
        "Какое число будет следующим: {sequence}?",
        "Найди следующий элемент ряда: {sequence}.",
    )
    prompt = rng.choice(templates).format(sequence=sequence)

    return TrainingExample(
        id=f"sequence.decreasing_progression:{index:08d}",
        task_type="sequence.decreasing_progression",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(answer),
        metadata={"start": start, "step": step, "length": length},
    )


def generate_missing_middle(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    start = profile.randint(rng, 0, 20)
    step = profile.randint(rng, 1, 10)
    numbers = [start + step * offset for offset in range(4)]
    missing_index = rng.randint(1, 2)
    answer = numbers[missing_index]
    shown = [
        "□" if offset == missing_index else str(number)
        for offset, number in enumerate(numbers)
    ]
    sequence = ", ".join(shown)
    templates = (
        "Какое число пропущено: {sequence}?",
        "Вставь пропущенное число в ряд: {sequence}.",
        "Найди число вместо квадрата: {sequence}.",
    )
    prompt = rng.choice(templates).format(sequence=sequence)

    return TrainingExample(
        id=f"sequence.missing_middle:{index:08d}",
        task_type="sequence.missing_middle",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=str(answer),
        metadata={"numbers": numbers, "missing_index": missing_index},
    )


def generate_alternating_words(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    first, second = rng.sample(COLORS, 2)
    sequence = [first, second, first, second]
    templates = (
        "Продолжи последовательность: {sequence}.",
        "Какое слово будет следующим: {sequence}?",
        "Найди повторяющийся порядок и продолжи: {sequence}.",
    )
    prompt = rng.choice(templates).format(sequence=", ".join(sequence))

    return TrainingExample(
        id=f"sequence.alternating_words:{index:08d}",
        task_type="sequence.alternating_words",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=first,
        metadata={"pattern": [first, second], "operation": "continue_alternation"},
    )


def generate_repeat_pattern(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    pattern = rng.sample(COLORS, 3)
    sequence = pattern + pattern[:2]
    templates = (
        "Продолжи повторяющийся ряд: {sequence}.",
        "Что идёт дальше в повторе: {sequence}?",
        "Найди шаблон и добавь следующее слово: {sequence}.",
    )
    prompt = rng.choice(templates).format(sequence=", ".join(sequence))

    return TrainingExample(
        id=f"sequence.repeat_pattern:{index:08d}",
        task_type="sequence.repeat_pattern",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=pattern[2],
        metadata={"pattern": pattern, "operation": "repeat_pattern"},
    )


def generate_direct_quantity(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_quantity_fact(subject, noun, count)
    question = _quantity_question(subject, noun)

    return TrainingExample(
        id=f"quantity.direct:{index:08d}",
        task_type="quantity.direct",
        prompt=f"{fact} {question}",
        answer=str(count),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "known",
            "subject": subject.nominative,
            "subject_genitive": subject.genitive,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_quantity_irrelevant_subject(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    fact_subject, question_subject = _pick_distinct_people(rng, 2)
    noun = rng.choice(COUNTED_NOUNS)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_quantity_fact(fact_subject, noun, count)
    question = _quantity_question(question_subject, noun)

    return TrainingExample(
        id=f"quantity.irrelevant_subject:{index:08d}",
        task_type="quantity.irrelevant_subject",
        prompt=f"{fact} {question}",
        answer=_insufficient_answer(
            f"сказано про {fact_subject.accusative}, а вопрос про {question_subject.accusative}"
        ),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "irrelevant_subject",
            "fact_subject": fact_subject.nominative,
            "question_subject": question_subject.nominative,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_quantity_object_mismatch(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    fact_noun, question_noun = _pick_distinct_nouns(rng, 2)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_quantity_fact(subject, fact_noun, count)
    question = _quantity_question(subject, question_noun)

    return TrainingExample(
        id=f"quantity.object_mismatch:{index:08d}",
        task_type="quantity.object_mismatch",
        prompt=f"{fact} {question}",
        answer=_insufficient_answer(
            f"сказано про предмет «{fact_noun.one}», а вопрос про предмет «{question_noun.one}»"
        ),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "object_mismatch",
            "subject": subject.nominative,
            "fact_noun": fact_noun.many,
            "question_noun": question_noun.many,
            "count": count,
            "be_verb": be_verb,
        },
    )


def generate_location_direct(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    location = rng.choice(LOCATIONS)
    noun = rng.choice(COUNTED_NOUNS)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_location_quantity_fact(location, noun, count)
    question = _location_quantity_question(location, noun)

    return TrainingExample(
        id=f"quantity.location_direct:{index:08d}",
        task_type="quantity.location_direct",
        prompt=f"{fact} {question}",
        answer=str(count),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "known",
            "location": location.name,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_location_mismatch(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    fact_location, question_location = _pick_distinct_locations(rng, 2)
    noun = rng.choice(COUNTED_NOUNS)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_location_quantity_fact(fact_location, noun, count)
    question = _location_quantity_question(question_location, noun)

    return TrainingExample(
        id=f"quantity.location_mismatch:{index:08d}",
        task_type="quantity.location_mismatch",
        prompt=f"{fact} {question}",
        answer=_insufficient_answer(
            f"сказано про место «{fact_location.name}», а вопрос про место «{question_location.name}»"
        ),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "location_mismatch",
            "fact_location": fact_location.name,
            "question_location": question_location.name,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_time_past_unknown(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_quantity_fact(subject, noun, count)
    fact = f"Вчера {fact[0].lower()}{fact[1:]}"
    question = f"Сколько {noun.question} у {subject.genitive} сейчас?"

    return TrainingExample(
        id=f"quantity.time_past_unknown:{index:08d}",
        task_type="quantity.time_past_unknown",
        prompt=f"{fact} {question}",
        answer=_insufficient_answer("известно прошлое состояние, но не текущее"),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "time_mismatch",
            "subject": subject.nominative,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_state_change_add(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    start = profile.randint(rng, 0, 20)
    delta = profile.randint(rng, 1, 10)
    fact, be_verb = _make_quantity_fact(subject, noun, start)
    change = f"{subject.dative} дали ещё {format_counted_noun_accusative(delta, noun)}."
    question = f"Сколько {noun.question} стало у {subject.genitive}?"

    return TrainingExample(
        id=f"state_change.add:{index:08d}",
        task_type="state_change.add",
        prompt=f"{fact} {change} {question}",
        answer=str(start + delta),
        metadata={
            "subject": subject.nominative,
            "noun": noun.many,
            "start": start,
            "delta": delta,
            "operation": "state_add",
            "be_verb": be_verb,
        },
    )


def generate_state_change_subtract(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    start = profile.randint(rng, 1, 20)
    delta = rng.randint(1, start)
    fact, be_verb = _make_quantity_fact(subject, noun, start)
    change = (
        f"У {subject.genitive} забрали {format_counted_noun_accusative(delta, noun)}."
    )
    question = f"Сколько {noun.question} осталось у {subject.genitive}?"

    return TrainingExample(
        id=f"state_change.subtract:{index:08d}",
        task_type="state_change.subtract",
        prompt=f"{fact} {change} {question}",
        answer=str(start - delta),
        metadata={
            "subject": subject.nominative,
            "noun": noun.many,
            "start": start,
            "delta": delta,
            "operation": "state_subtract",
            "be_verb": be_verb,
        },
    )


def generate_state_change_other_subject_no_change(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    target, other = _pick_distinct_people(rng, 2)
    noun = rng.choice(COUNTED_NOUNS)
    start = profile.randint(rng, 1, 20)
    delta = profile.randint(rng, 1, 10)
    fact, be_verb = _make_quantity_fact(target, noun, start)
    change = f"{other.dative} дали ещё {format_counted_noun_accusative(delta, noun)}."
    question = f"Сколько {noun.question} стало у {target.genitive}?"

    return TrainingExample(
        id=f"state_change.other_subject_no_change:{index:08d}",
        task_type="state_change.other_subject_no_change",
        prompt=f"{fact} {change} {question}",
        answer=str(start),
        metadata={
            "target_subject": target.nominative,
            "changed_subject": other.nominative,
            "noun": noun.many,
            "start": start,
            "delta": delta,
            "operation": "ignore_other_subject_change",
            "be_verb": be_verb,
        },
    )


def generate_state_change_other_object_no_change(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    target_noun, other_noun = _pick_distinct_nouns(rng, 2)
    start = profile.randint(rng, 1, 20)
    delta = profile.randint(rng, 1, 10)
    fact, be_verb = _make_quantity_fact(subject, target_noun, start)
    change = f"{subject.dative} дали ещё {format_counted_noun_accusative(delta, other_noun)}."
    question = f"Сколько {target_noun.question} стало у {subject.genitive}?"

    return TrainingExample(
        id=f"state_change.other_object_no_change:{index:08d}",
        task_type="state_change.other_object_no_change",
        prompt=f"{fact} {change} {question}",
        answer=str(start),
        metadata={
            "subject": subject.nominative,
            "target_noun": target_noun.many,
            "changed_noun": other_noun.many,
            "start": start,
            "delta": delta,
            "operation": "ignore_other_object_change",
            "be_verb": be_verb,
        },
    )


def generate_state_change_insufficient_start(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    delta = profile.randint(rng, 1, 10)
    change = f"{subject.dative} дали ещё {format_counted_noun_accusative(delta, noun)}."
    question = f"Сколько {noun.question} стало у {subject.genitive}?"

    return TrainingExample(
        id=f"state_change.insufficient_start:{index:08d}",
        task_type="state_change.insufficient_start",
        prompt=f"{change} {question}",
        answer=_insufficient_answer("неизвестно, сколько было сначала"),
        metadata={
            "subject": subject.nominative,
            "noun": noun.many,
            "delta": delta,
            "epistemic_state": "unknown_start",
        },
    )


def generate_insufficient_info(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    item = rng.choice(OBJECT_PROPERTIES)
    templates = (
        "Известен только предмет у {genitive}: {noun}. {question}",
        "У {genitive} появился предмет: {noun}. {question}",
        "Сказано только, что у {genitive} есть {noun}. {question}",
    )
    prompt = rng.choice(templates).format(
        subject=subject.nominative,
        genitive=subject.genitive,
        noun=item.noun,
        question=item.question,
    )

    return TrainingExample(
        id=f"epistemic.insufficient_info:{index:08d}",
        task_type="epistemic.insufficient_info",
        prompt=_case_prefix(rng, profile) + prompt,
        answer="Недостаточно информации.",
        metadata={
            "epistemic_state": "unknown",
            "subject": subject.nominative,
            "object": item.noun,
            "unknown_property": item.property_name,
        },
    )


def generate_irrelevant_fact(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    fact_subject, question_subject = _pick_distinct_people(rng, 2)
    noun = rng.choice(COUNTED_NOUNS)
    count = profile.randint(rng, 1, 20)
    fact, be_verb = _make_quantity_fact(fact_subject, noun, count)
    question = _quantity_question(question_subject, noun)

    return TrainingExample(
        id=f"epistemic.irrelevant_fact:{index:08d}",
        task_type="epistemic.irrelevant_fact",
        prompt=f"{fact} {question}",
        answer=_insufficient_answer(
            f"сказано про {fact_subject.accusative}, а вопрос про {question_subject.accusative}"
        ),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "irrelevant_subject",
            "fact_subject": fact_subject.nominative,
            "question_subject": question_subject.nominative,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_known_zero_quantity(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    prompt = (
        f"Сказано, что у {subject.genitive} не было {noun.question}. "
        f"Сколько {noun.question} было у {subject.genitive}?"
    )

    return TrainingExample(
        id=f"quantity.known_zero:{index:08d}",
        task_type="quantity.known_zero",
        prompt=_case_prefix(rng, profile) + prompt,
        answer="0",
        metadata={
            "epistemic_state": "known_zero",
            "subject": subject.nominative,
            "noun": noun.many,
        },
    )


def generate_false_presupposition(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    prompt = (
        f"Сказано, что у {subject.genitive} не было {noun.question}. "
        f"Какой был цвет этих {noun.question}?"
    )

    return TrainingExample(
        id=f"epistemic.false_presupposition:{index:08d}",
        task_type="epistemic.false_presupposition",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=(
            "Ложная предпосылка: "
            f"сказано, что у {subject.genitive} не было {noun.question}."
        ),
        metadata={
            "epistemic_state": "false_presupposition",
            "subject": subject.nominative,
            "noun": noun.many,
        },
    )


def generate_contradiction(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    first_count = profile.randint(rng, 1, 20)
    second_count = profile.randint(rng, 1, 20)

    while second_count == first_count:
        second_count = profile.randint(rng, 1, 20)

    first_fact, _ = _make_quantity_fact(subject, noun, first_count)
    second_fact, _ = _make_quantity_fact(subject, noun, second_count)
    prompt = f"{first_fact} В тот же момент {second_fact[0].lower()}{second_fact[1:]} Это возможно?"

    return TrainingExample(
        id=f"epistemic.contradiction:{index:08d}",
        task_type="epistemic.contradiction",
        prompt=_case_prefix(rng, profile) + prompt,
        answer="Противоречие: для одного субъекта и предмета указаны разные количества.",
        metadata={
            "epistemic_state": "contradiction",
            "subject": subject.nominative,
            "noun": noun.many,
            "first_count": first_count,
            "second_count": second_count,
        },
    )


def generate_logic_transitive_height(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    high, middle, low = _pick_distinct_people(rng, 3)
    prompt = (
        f"{high.nominative} выше {middle.genitive}. "
        f"{middle.nominative} выше {low.genitive}. Кто самый высокий?"
    )

    return TrainingExample(
        id=f"logic.transitive_height:{index:08d}",
        task_type="logic.transitive_height",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=high.nominative,
        metadata={
            "relation": "higher_than",
            "high": high.nominative,
            "middle": middle.nominative,
            "low": low.nominative,
        },
    )


def generate_logic_all_category(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    rule = rng.choice(CATEGORY_RULES)
    templates = (
        "Все {member_many} — {category_many}. {example} — {member_one}. {example} — {category_one}?",
        "Каждый объект типа «{member_one}» относится к типу «{category_one}». {example} — {member_one}. Значит ли это, что {example} относится к типу «{category_one}»?",
    )
    prompt = rng.choice(templates).format(
        member_one=rule.member_one,
        member_many=rule.member_many,
        category_one=rule.category_one,
        category_many=rule.category_many,
        example=rule.example_name,
    )

    return TrainingExample(
        id=f"logic.all_category:{index:08d}",
        task_type="logic.all_category",
        prompt=_case_prefix(rng, profile) + prompt,
        answer="Да.",
        metadata={
            "relation": "category_inclusion",
            "member": rule.member_one,
            "category": rule.category_one,
            "example": rule.example_name,
        },
    )


def generate_logic_negation(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    prompt = (
        f"У {subject.genitive} не было {noun.question}. "
        f"Можно ли утверждать, что количество {noun.question} у {subject.genitive} было больше нуля?"
    )

    return TrainingExample(
        id=f"logic.negation:{index:08d}",
        task_type="logic.negation",
        prompt=_case_prefix(rng, profile) + prompt,
        answer="Нет.",
        metadata={
            "operation": "negation",
            "subject": subject.nominative,
            "noun": noun.many,
        },
    )


def generate_logic_and_or(
    rng: random.Random,
    index: int,
    profile: GenerationProfile = TRAIN_PROFILE,
) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    first_fact, second_fact = rng.choice(
        (
            ("лампа горит", "дверь открыта"),
            ("окно закрыто", "стол чистый"),
            ("звонок прозвенел", "урок начался"),
            ("книга лежит на столе", "тетрадь лежит в рюкзаке"),
        )
    )

    if rng.choice((True, False)):
        prompt = (
            f"Известно: у {subject.genitive} верны два факта — {first_fact} и {second_fact}. "
            f"Можно ли точно сказать, что факт «{first_fact}» верен?"
        )
        answer = "Да."
        operator = "and"
    else:
        prompt = (
            f"Известно: у {subject.genitive} верен хотя бы один факт — {first_fact} или {second_fact}. "
            f"Можно ли точно сказать, что факт «{first_fact}» верен?"
        )
        answer = _insufficient_answer(
            "из союза «или» не следует, какой именно факт верен"
        )
        operator = "or"

    return TrainingExample(
        id=f"logic.and_or:{index:08d}",
        task_type="logic.and_or",
        prompt=_case_prefix(rng, profile) + prompt,
        answer=answer,
        metadata={
            "operation": operator,
            "subject": subject.nominative,
            "first_fact": first_fact,
            "second_fact": second_fact,
        },
    )


GENERATOR_FUNCTIONS: dict[GeneratorName, GeneratorFunction] = {
    "comparison.max": generate_comparison_max,
    "comparison.min": generate_comparison_min,
    "comparison.equality": generate_comparison_equality,
    "comparison.three_max": generate_comparison_three_max,
    "comparison.three_min": generate_comparison_three_min,
    "sorting.ascending": generate_sorting_ascending,
    "sorting.descending": generate_sorting_descending,
    "order.before_after": generate_order_before_after,
    "arithmetic.add": generate_addition,
    "arithmetic.subtract": generate_subtraction,
    "arithmetic.missing_addend": generate_missing_addend,
    "arithmetic.compare_sum": generate_compare_sum,
    "arithmetic.double_step": generate_double_step,
    "sequence.arithmetic_progression": generate_arithmetic_progression,
    "sequence.decreasing_progression": generate_decreasing_progression,
    "sequence.missing_middle": generate_missing_middle,
    "sequence.alternating_words": generate_alternating_words,
    "sequence.repeat_pattern": generate_repeat_pattern,
    "quantity.direct": generate_direct_quantity,
    "quantity.irrelevant_subject": generate_quantity_irrelevant_subject,
    "quantity.object_mismatch": generate_quantity_object_mismatch,
    "quantity.location_direct": generate_location_direct,
    "quantity.location_mismatch": generate_location_mismatch,
    "quantity.time_past_unknown": generate_time_past_unknown,
    "quantity.known_zero": generate_known_zero_quantity,
    "state_change.add": generate_state_change_add,
    "state_change.subtract": generate_state_change_subtract,
    "state_change.other_subject_no_change": generate_state_change_other_subject_no_change,
    "state_change.other_object_no_change": generate_state_change_other_object_no_change,
    "state_change.insufficient_start": generate_state_change_insufficient_start,
    "epistemic.insufficient_info": generate_insufficient_info,
    "epistemic.irrelevant_fact": generate_irrelevant_fact,
    "epistemic.false_presupposition": generate_false_presupposition,
    "epistemic.contradiction": generate_contradiction,
    "logic.transitive_height": generate_logic_transitive_height,
    "logic.all_category": generate_logic_all_category,
    "logic.negation": generate_logic_negation,
    "logic.and_or": generate_logic_and_or,
}

GENERATOR_NAMES: tuple[GeneratorName, ...] = tuple(GENERATOR_FUNCTIONS)


def generate_example(
    rng: random.Random,
    index: int,
    *,
    task_types: Sequence[GeneratorName] | None = None,
    profile: GenerationProfileName | GenerationProfile = "train",
) -> TrainingExample:
    allowed_task_types = tuple(task_types or GENERATOR_NAMES)
    generation_profile = resolve_generation_profile(profile)

    if not allowed_task_types:
        raise ValueError("task_types must not be empty")

    task_type = rng.choice(allowed_task_types)

    try:
        generator = GENERATOR_FUNCTIONS[task_type]
    except KeyError as error:
        raise ValueError(f"Unknown task type: {task_type}") from error

    return generator(rng, index, generation_profile)


def generate_examples(
    *,
    count: int,
    seed: int,
    task_types: Sequence[GeneratorName] | None = None,
    profile: GenerationProfileName | GenerationProfile = "train",
) -> list[TrainingExample]:
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = random.Random(seed)

    return [
        generate_example(rng, index, task_types=task_types, profile=profile)
        for index in range(count)
    ]
