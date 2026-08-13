from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Person:
    nominative: str
    genitive: str
    accusative: str


NounGender = Literal["masculine", "feminine", "neuter"]


@dataclass(frozen=True)
class CountedNoun:
    one: str
    few: str
    many: str
    question: str
    gender: NounGender


PEOPLE: tuple[Person, ...] = (
    Person(nominative="Вася", genitive="Васи", accusative="Васю"),
    Person(nominative="Ваня", genitive="Вани", accusative="Ваню"),
    Person(nominative="Лена", genitive="Лены", accusative="Лену"),
    Person(nominative="Маша", genitive="Маши", accusative="Машу"),
    Person(nominative="Петя", genitive="Пети", accusative="Петю"),
    Person(nominative="Коля", genitive="Коли", accusative="Колю"),
    Person(nominative="Даша", genitive="Даши", accusative="Дашу"),
    Person(nominative="Оля", genitive="Оли", accusative="Олю"),
    Person(nominative="Ира", genitive="Иры", accusative="Иру"),
    Person(nominative="Саша", genitive="Саши", accusative="Сашу"),
    Person(nominative="Антон", genitive="Антона", accusative="Антона"),
    Person(nominative="Дима", genitive="Димы", accusative="Диму"),
    Person(nominative="Юля", genitive="Юли", accusative="Юлю"),
    Person(nominative="Рома", genitive="Ромы", accusative="Рому"),
    Person(nominative="Катя", genitive="Кати", accusative="Катю"),
    Person(nominative="Нина", genitive="Нины", accusative="Нину"),
)


COUNTED_NOUNS: tuple[CountedNoun, ...] = (
    CountedNoun(
        one="мороженое",
        few="мороженых",
        many="мороженых",
        question="мороженых",
        gender="neuter",
    ),
    CountedNoun(
        one="карандаш",
        few="карандаша",
        many="карандашей",
        question="карандашей",
        gender="masculine",
    ),
    CountedNoun(
        one="монета",
        few="монеты",
        many="монет",
        question="монет",
        gender="feminine",
    ),
    CountedNoun(
        one="яблоко",
        few="яблока",
        many="яблок",
        question="яблок",
        gender="neuter",
    ),
    CountedNoun(
        one="конфета",
        few="конфеты",
        many="конфет",
        question="конфет",
        gender="feminine",
    ),
    CountedNoun(
        one="кубик",
        few="кубика",
        many="кубиков",
        question="кубиков",
        gender="masculine",
    ),
    CountedNoun(
        one="книга",
        few="книги",
        many="книг",
        question="книг",
        gender="feminine",
    ),
    CountedNoun(
        one="рубль",
        few="рубля",
        many="рублей",
        question="рублей",
        gender="masculine",
    ),
    CountedNoun(
        one="печенье",
        few="печенья",
        many="печений",
        question="печений",
        gender="neuter",
    ),
)


def choose_counted_noun_form(count: int, noun: CountedNoun) -> str:
    absolute_count = abs(count)
    last_two_digits = absolute_count % 100

    if 11 <= last_two_digits <= 14:
        return noun.many

    last_digit = absolute_count % 10

    if last_digit == 1:
        return noun.one

    if 2 <= last_digit <= 4:
        return noun.few

    return noun.many


def format_counted_noun(count: int, noun: CountedNoun) -> str:
    return f"{count} {choose_counted_noun_form(count, noun)}"


def is_singular_one(count: int) -> bool:
    absolute_count = abs(count)
    last_two_digits = absolute_count % 100

    if 11 <= last_two_digits <= 14:
        return False

    return absolute_count % 10 == 1


def choose_past_be_verb(count: int, noun: CountedNoun) -> str:
    if not is_singular_one(count):
        return "было"

    if noun.gender == "masculine":
        return "был"

    if noun.gender == "feminine":
        return "была"

    return "было"
