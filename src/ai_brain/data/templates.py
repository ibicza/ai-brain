from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    nominative: str
    genitive: str
    accusative: str


@dataclass(frozen=True)
class CountedNoun:
    one: str
    few: str
    many: str
    question: str


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
        one="мороженое", few="мороженых", many="мороженых", question="мороженых"
    ),
    CountedNoun(
        one="карандаш", few="карандаша", many="карандашей", question="карандашей"
    ),
    CountedNoun(one="монета", few="монеты", many="монет", question="монет"),
    CountedNoun(one="яблоко", few="яблока", many="яблок", question="яблок"),
    CountedNoun(one="конфета", few="конфеты", many="конфет", question="конфет"),
    CountedNoun(one="кубик", few="кубика", many="кубиков", question="кубиков"),
    CountedNoun(one="книга", few="книги", many="книг", question="книг"),
    CountedNoun(one="рубль", few="рубля", many="рублей", question="рублей"),
    CountedNoun(one="печенье", few="печенья", many="печений", question="печений"),
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
