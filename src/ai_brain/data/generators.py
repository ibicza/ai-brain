from __future__ import annotations

import random
from collections.abc import Sequence

from ai_brain.data.schema import TrainingExample
from ai_brain.data.templates import (
    COUNTED_NOUNS,
    PEOPLE,
    choose_past_be_verb,
    format_counted_noun,
)

GeneratorName = str

GENERATOR_NAMES: tuple[GeneratorName, ...] = (
    "comparison.max",
    "arithmetic.add",
    "sequence.arithmetic_progression",
    "quantity.direct",
    "epistemic.insufficient_info",
    "epistemic.irrelevant_fact",
)


def generate_comparison_max(rng: random.Random, index: int) -> TrainingExample:
    a = rng.randint(0, 99)
    b = rng.randint(0, 99)

    while b == a:
        b = rng.randint(0, 99)

    answer = str(max(a, b))

    return TrainingExample(
        id=f"comparison.max:{index:08d}",
        task_type="comparison.max",
        prompt=f"Что больше: {a} или {b}?",
        answer=answer,
        metadata={
            "a": a,
            "b": b,
            "operation": "max",
        },
    )


def generate_addition(rng: random.Random, index: int) -> TrainingExample:
    a = rng.randint(0, 20)
    b = rng.randint(0, 20)

    return TrainingExample(
        id=f"arithmetic.add:{index:08d}",
        task_type="arithmetic.add",
        prompt=f"Сколько будет {a} + {b}?",
        answer=str(a + b),
        metadata={
            "a": a,
            "b": b,
            "operation": "addition",
        },
    )


def generate_arithmetic_progression(
    rng: random.Random,
    index: int,
) -> TrainingExample:
    start = rng.randint(0, 20)
    step = rng.randint(1, 10)
    length = 4

    numbers = [start + step * offset for offset in range(length)]
    answer = start + step * length

    sequence = ", ".join(str(number) for number in numbers)

    return TrainingExample(
        id=f"sequence.arithmetic_progression:{index:08d}",
        task_type="sequence.arithmetic_progression",
        prompt=f"Продолжи последовательность: {sequence}.",
        answer=str(answer),
        metadata={
            "start": start,
            "step": step,
            "length": length,
            "operation": "next_arithmetic_progression_item",
        },
    )


def generate_direct_quantity(rng: random.Random, index: int) -> TrainingExample:
    subject = rng.choice(PEOPLE)
    noun = rng.choice(COUNTED_NOUNS)
    count = rng.randint(1, 20)

    counted_noun = format_counted_noun(count, noun)

    be_verb = choose_past_be_verb(count, noun)

    fact = f"У {subject.genitive} {be_verb} {counted_noun}."
    question = f"Сколько {noun.question} было у {subject.genitive}?"

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


def generate_insufficient_info(rng: random.Random, index: int) -> TrainingExample:
    variants = [
        ("Вася купил машину.", "Какого цвета машина Васи?"),
        ("Лена взяла книгу.", "Сколько страниц в книге Лены?"),
        ("Петя нашёл коробку.", "Что лежит в коробке Пети?"),
        ("Маша увидела собаку.", "Какой породы собака, которую увидела Маша?"),
        ("Ваня купил дом.", "Какой площади дом Вани?"),
        ("Лена взяла яблоко.", "Какого цвета яблоко Лены?"),
        ("Петя нашёл купюру.", "Какой номинал купюры Пети?"),
        ("Маша увидела облако.", "Какой формы облако, которое увидела Маша?"),
        ("Олег купил телефон.", "Какой марки телефон Олега?"),
        ("Катя нашла ключ.", "От какой двери ключ Кати?"),
        ("Ира увидела птицу.", "Какого цвета была птица?"),
        ("Дима взял пакет.", "Что лежит в пакете Димы?"),
        ("Нина получила письмо.", "Кто написал письмо Нине?"),
        ("Антон услышал звук.", "Что издало звук, который услышал Антон?"),
        ("Саша открыл ящик.", "Что было внутри ящика?"),
        ("Таня увидела дом.", "Сколько этажей было в доме?"),
        ("Коля купил билет.", "На какое место билет Коли?"),
        ("Аня взяла чашку.", "Из какого материала чашка Ани?"),
        ("Витя нашёл камень.", "Сколько весит камень Вити?"),
        ("Оля увидела реку.", "Какая глубина у реки?"),
        ("Гена взял тетрадь.", "Сколько страниц в тетради Гены?"),
        ("Марина купила цветок.", "Как называется цветок Марины?"),
        ("Павел увидел корабль.", "Куда плыл корабль?"),
        ("Юля нашла фотографию.", "Кто изображён на фотографии Юли?"),
        ("Рома взял коробку конфет.", "Сколько конфет было в коробке?"),
        ("Лиза услышала голос.", "Кому принадлежал голос?"),
        ("Миша увидел автобус.", "Какой номер был у автобуса?"),
        ("Света купила ручку.", "Какого цвета паста в ручке Светы?"),
        ("Игорь нашёл карту.", "Какой город был отмечен на карте?"),
        ("Даша взяла игрушку.", "Из чего сделана игрушка Даши?"),
        ("Кирилл увидел велосипед.", "Сколько скоростей у велосипеда?"),
        ("Настя получила подарок.", "Что было в подарке Насти?"),
        ("Боря открыл книгу.", "На какой странице Боря открыл книгу?"),
        ("Алёна увидела кошку.", "Как зовут кошку, которую увидела Алёна?"),
        ("Федя нашёл сумку.", "Кому принадлежит сумка Феди?"),
        ("Вера купила мороженое.", "Какой вкус у мороженого Веры?"),
    ]
    fact, question = rng.choice(variants)

    return TrainingExample(
        id=f"epistemic.insufficient_info:{index:08d}",
        task_type="epistemic.insufficient_info",
        prompt=f"{fact} {question}",
        answer="Недостаточно информации.",
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "unknown",
        },
    )


def generate_irrelevant_fact(rng: random.Random, index: int) -> TrainingExample:
    fact_subject, question_subject = rng.sample(PEOPLE, 2)
    noun = rng.choice(COUNTED_NOUNS)
    count = rng.randint(1, 20)

    counted_noun = format_counted_noun(count, noun)

    be_verb = choose_past_be_verb(count, noun)

    fact = f"У {fact_subject.genitive} {be_verb} {counted_noun}."
    question = f"Сколько {noun.question} было у {question_subject.genitive}?"

    return TrainingExample(
        id=f"epistemic.irrelevant_fact:{index:08d}",
        task_type="epistemic.irrelevant_fact",
        prompt=f"{fact} {question}",
        answer=(
            "Недостаточно информации: "
            f"сказано про {fact_subject.accusative}, "
            f"а вопрос про {question_subject.accusative}."
        ),
        metadata={
            "known_fact": fact,
            "question": question,
            "epistemic_state": "irrelevant_fact",
            "fact_subject": fact_subject.nominative,
            "question_subject": question_subject.nominative,
            "count": count,
            "noun": noun.many,
            "be_verb": be_verb,
        },
    )


def generate_example(
    rng: random.Random,
    index: int,
    *,
    task_types: Sequence[GeneratorName] | None = None,
) -> TrainingExample:
    allowed_task_types = tuple(task_types or GENERATOR_NAMES)

    if not allowed_task_types:
        raise ValueError("task_types must not be empty")

    task_type = rng.choice(allowed_task_types)

    if task_type == "comparison.max":
        return generate_comparison_max(rng, index)

    if task_type == "arithmetic.add":
        return generate_addition(rng, index)

    if task_type == "sequence.arithmetic_progression":
        return generate_arithmetic_progression(rng, index)

    if task_type == "quantity.direct":
        return generate_direct_quantity(rng, index)

    if task_type == "epistemic.insufficient_info":
        return generate_insufficient_info(rng, index)

    if task_type == "epistemic.irrelevant_fact":
        return generate_irrelevant_fact(rng, index)

    raise ValueError(f"Unknown task type: {task_type}")


def generate_examples(
    *,
    count: int,
    seed: int,
    task_types: Sequence[GeneratorName] | None = None,
) -> list[TrainingExample]:
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = random.Random(seed)

    return [
        generate_example(rng, index, task_types=task_types) for index in range(count)
    ]
