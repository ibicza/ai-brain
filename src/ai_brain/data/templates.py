from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Person:
    nominative: str
    genitive: str
    accusative: str
    dative: str
    instrumental: str


NounGender = Literal["masculine", "feminine", "neuter"]


@dataclass(frozen=True)
class CountedNoun:
    one: str
    few: str
    many: str
    question: str
    gender: NounGender
    accusative_one: str | None = None


@dataclass(frozen=True)
class Location:
    name: str
    where: str


@dataclass(frozen=True)
class ObjectProperty:
    noun: str
    property_name: str
    question: str


@dataclass(frozen=True)
class CategoryRule:
    member_one: str
    member_many: str
    category_one: str
    category_many: str
    example_name: str


PEOPLE: tuple[Person, ...] = (
    Person(
        nominative="Вася",
        genitive="Васи",
        accusative="Васю",
        dative="Васе",
        instrumental="Васей",
    ),
    Person(
        nominative="Ваня",
        genitive="Вани",
        accusative="Ваню",
        dative="Ване",
        instrumental="Ваней",
    ),
    Person(
        nominative="Лена",
        genitive="Лены",
        accusative="Лену",
        dative="Лене",
        instrumental="Леной",
    ),
    Person(
        nominative="Маша",
        genitive="Маши",
        accusative="Машу",
        dative="Маше",
        instrumental="Машей",
    ),
    Person(
        nominative="Петя",
        genitive="Пети",
        accusative="Петю",
        dative="Пете",
        instrumental="Петей",
    ),
    Person(
        nominative="Коля",
        genitive="Коли",
        accusative="Колю",
        dative="Коле",
        instrumental="Колей",
    ),
    Person(
        nominative="Даша",
        genitive="Даши",
        accusative="Дашу",
        dative="Даше",
        instrumental="Дашей",
    ),
    Person(
        nominative="Оля",
        genitive="Оли",
        accusative="Олю",
        dative="Оле",
        instrumental="Олей",
    ),
    Person(
        nominative="Ира",
        genitive="Иры",
        accusative="Иру",
        dative="Ире",
        instrumental="Ирой",
    ),
    Person(
        nominative="Саша",
        genitive="Саши",
        accusative="Сашу",
        dative="Саше",
        instrumental="Сашей",
    ),
    Person(
        nominative="Антон",
        genitive="Антона",
        accusative="Антона",
        dative="Антону",
        instrumental="Антоном",
    ),
    Person(
        nominative="Дима",
        genitive="Димы",
        accusative="Диму",
        dative="Диме",
        instrumental="Димой",
    ),
    Person(
        nominative="Юля",
        genitive="Юли",
        accusative="Юлю",
        dative="Юле",
        instrumental="Юлей",
    ),
    Person(
        nominative="Рома",
        genitive="Ромы",
        accusative="Рому",
        dative="Роме",
        instrumental="Ромой",
    ),
    Person(
        nominative="Катя",
        genitive="Кати",
        accusative="Катю",
        dative="Кате",
        instrumental="Катей",
    ),
    Person(
        nominative="Нина",
        genitive="Нины",
        accusative="Нину",
        dative="Нине",
        instrumental="Ниной",
    ),
    Person(
        nominative="Олег",
        genitive="Олега",
        accusative="Олега",
        dative="Олегу",
        instrumental="Олегом",
    ),
    Person(
        nominative="Игорь",
        genitive="Игоря",
        accusative="Игоря",
        dative="Игорю",
        instrumental="Игорем",
    ),
    Person(
        nominative="Алёна",
        genitive="Алёны",
        accusative="Алёну",
        dative="Алёне",
        instrumental="Алёной",
    ),
    Person(
        nominative="Вера",
        genitive="Веры",
        accusative="Веру",
        dative="Вере",
        instrumental="Верой",
    ),
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
        accusative_one="монету",
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
        accusative_one="конфету",
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
        accusative_one="книгу",
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
    CountedNoun(
        one="камень",
        few="камня",
        many="камней",
        question="камней",
        gender="masculine",
    ),
    CountedNoun(
        one="игрушка",
        few="игрушки",
        many="игрушек",
        question="игрушек",
        gender="feminine",
        accusative_one="игрушку",
    ),
    CountedNoun(
        one="тетрадь",
        few="тетради",
        many="тетрадей",
        question="тетрадей",
        gender="feminine",
        accusative_one="тетрадь",
    ),
)


LOCATIONS: tuple[Location, ...] = (
    Location(name="коробка", where="в коробке"),
    Location(name="пакет", where="в пакете"),
    Location(name="шкаф", where="в шкафу"),
    Location(name="ящик", where="в ящике"),
    Location(name="рюкзак", where="в рюкзаке"),
    Location(name="сумка", where="в сумке"),
    Location(name="стол", where="на столе"),
    Location(name="полка", where="на полке"),
    Location(name="сад", where="в саду"),
    Location(name="комната", where="в комнате"),
)


OBJECT_PROPERTIES: tuple[ObjectProperty, ...] = (
    ObjectProperty(
        noun="машина", property_name="цвет", question="Какого цвета машина?"
    ),
    ObjectProperty(
        noun="книга", property_name="число страниц", question="Сколько страниц в книге?"
    ),
    ObjectProperty(
        noun="коробка", property_name="содержимое", question="Что лежит в коробке?"
    ),
    ObjectProperty(
        noun="собака", property_name="порода", question="Какой породы собака?"
    ),
    ObjectProperty(noun="дом", property_name="площадь", question="Какой площади дом?"),
    ObjectProperty(noun="птица", property_name="цвет", question="Какого цвета птица?"),
    ObjectProperty(noun="ключ", property_name="дверь", question="От какой двери ключ?"),
    ObjectProperty(
        noun="подарок", property_name="содержимое", question="Что было в подарке?"
    ),
)


CATEGORY_RULES: tuple[CategoryRule, ...] = (
    CategoryRule(
        member_one="воробей",
        member_many="воробьи",
        category_one="птица",
        category_many="птицы",
        example_name="Кеша",
    ),
    CategoryRule(
        member_one="окунь",
        member_many="окуни",
        category_one="рыба",
        category_many="рыбы",
        example_name="Бим",
    ),
    CategoryRule(
        member_one="дуб",
        member_many="дубы",
        category_one="дерево",
        category_many="деревья",
        example_name="Старый дуб",
    ),
    CategoryRule(
        member_one="роза",
        member_many="розы",
        category_one="цветок",
        category_many="цветы",
        example_name="Алая роза",
    ),
)


COLORS: tuple[str, ...] = (
    "красный",
    "синий",
    "зелёный",
    "жёлтый",
    "белый",
    "чёрный",
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


def choose_counted_noun_accusative_form(count: int, noun: CountedNoun) -> str:
    if is_singular_one(count):
        return noun.accusative_one or noun.one

    return choose_counted_noun_form(count, noun)


def format_counted_noun(count: int, noun: CountedNoun) -> str:
    return f"{count} {choose_counted_noun_form(count, noun)}"


def format_counted_noun_accusative(count: int, noun: CountedNoun) -> str:
    return f"{count} {choose_counted_noun_accusative_form(count, noun)}"


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
