"""Stack-bounded recursive-descent parser for neutral educational formulas."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict

from ai_brain.stage2.domains.chemistry.models import (
    CompositionEntry,
    ElementTerm,
    FormulaAst,
    FormulaLimits,
    GroupTerm,
)
from ai_brain.stage2.domains.chemistry.version import CHEMISTRY_FORMULA_GRAMMAR_VERSION
from ai_brain.stage2.facts.canonical import content_hash


class FormulaParseError(ValueError):
    def __init__(self, code: str, position: int, message: str) -> None:
        self.code = code
        self.position = position
        super().__init__(f"{code} at position {position}: {message}")


class FormulaResourceLimitError(FormulaParseError):
    pass


class FormulaParser:
    def __init__(
        self,
        supported_symbols: set[str] | frozenset[str],
        limits: FormulaLimits | None = None,
    ) -> None:
        self.supported_symbols = frozenset(supported_symbols)
        self.limits = limits or FormulaLimits()
        if not self.supported_symbols:
            raise ValueError("supported symbol set must not be empty")

    def parse(self, formula: str) -> FormulaAst:
        if not isinstance(formula, str):
            raise TypeError("formula must be text")
        if not formula:
            raise FormulaParseError("EMPTY_FORMULA", 0, "formula is empty")
        if len(formula) > self.limits.max_input_chars:
            raise FormulaResourceLimitError(
                "INPUT_TOO_LONG",
                self.limits.max_input_chars,
                "formula exceeds input limit",
            )
        if any(char.isspace() for char in formula):
            raise FormulaParseError(
                "WHITESPACE_FORBIDDEN",
                next(i for i, c in enumerate(formula) if c.isspace()),
                "whitespace is not supported",
            )
        state = _ParserState(formula, self.supported_symbols, self.limits)
        terms = state.parse_terms(depth=0, closing=False)
        if state.position != len(formula):
            raise FormulaParseError(
                "TRAILING_INPUT", state.position, "input was not fully consumed"
            )
        composition = state.expand(terms)
        canonical = render_terms(terms)
        if len(canonical) > self.limits.max_canonical_output_chars:
            raise FormulaResourceLimitError(
                "CANONICAL_TOO_LONG", len(formula), "canonical output exceeds limit"
            )
        body = {
            "terms": terms,
            "composition": composition,
            "canonical_formula": canonical,
            "original_input_hash": content_hash(formula),
            "grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        }
        return FormulaAst(**body, ast_hash=content_hash(body))


class _ParserState:
    def __init__(
        self, text: str, symbols: frozenset[str], limits: FormulaLimits
    ) -> None:
        self.text = text
        self.symbols = symbols
        self.limits = limits
        self.position = 0
        self.groups = 0
        self.element_terms = 0

    def parse_terms(
        self, *, depth: int, closing: bool
    ) -> tuple[ElementTerm | GroupTerm, ...]:
        terms: list[ElementTerm | GroupTerm] = []
        while self.position < len(self.text):
            char = self.text[self.position]
            if char == ")":
                if not closing:
                    raise FormulaParseError(
                        "UNMATCHED_CLOSE",
                        self.position,
                        "unexpected closing parenthesis",
                    )
                break
            if char == "(":
                if depth >= self.limits.max_nesting_depth:
                    raise FormulaResourceLimitError(
                        "NESTING_LIMIT", self.position, "nesting depth exceeded"
                    )
                self.groups += 1
                if self.groups > self.limits.max_group_count:
                    raise FormulaResourceLimitError(
                        "GROUP_LIMIT", self.position, "group count exceeded"
                    )
                self.position += 1
                inner = self.parse_terms(depth=depth + 1, closing=True)
                if not inner:
                    raise FormulaParseError(
                        "EMPTY_GROUP", self.position, "empty groups are forbidden"
                    )
                if self.position >= len(self.text) or self.text[self.position] != ")":
                    raise FormulaParseError(
                        "UNMATCHED_OPEN", self.position, "missing closing parenthesis"
                    )
                self.position += 1
                terms.append(GroupTerm(inner, self.parse_multiplier()))
                continue
            if not char.isascii() or not char.isupper():
                raise FormulaParseError(
                    "EXPECTED_ELEMENT",
                    self.position,
                    "expected an exact-case element symbol",
                )
            symbol = char
            if (
                self.position + 1 < len(self.text)
                and self.text[self.position + 1].isascii()
                and self.text[self.position + 1].islower()
            ):
                symbol += self.text[self.position + 1]
            if symbol not in self.symbols:
                raise FormulaParseError(
                    "UNKNOWN_ELEMENT", self.position, f"unsupported element {symbol}"
                )
            self.position += len(symbol)
            self.element_terms += 1
            if self.element_terms > self.limits.max_element_terms:
                raise FormulaResourceLimitError(
                    "TERM_LIMIT", self.position, "element term count exceeded"
                )
            terms.append(ElementTerm(symbol, self.parse_multiplier()))
        return tuple(terms)

    def parse_multiplier(self) -> int:
        start = self.position
        while (
            self.position < len(self.text)
            and self.text[self.position].isascii()
            and self.text[self.position].isdigit()
        ):
            self.position += 1
        if start == self.position:
            return 1
        raw = self.text[start : self.position]
        if raw.startswith("0"):
            raise FormulaParseError(
                "INVALID_SUBSCRIPT",
                start,
                "subscript must be a positive integer without leading zero",
            )
        value = int(raw)
        if value > self.limits.max_subscript:
            raise FormulaResourceLimitError(
                "SUBSCRIPT_LIMIT", start, "subscript exceeds limit"
            )
        return value

    def expand(
        self, terms: tuple[ElementTerm | GroupTerm, ...]
    ) -> tuple[CompositionEntry, ...]:
        totals: dict[str, int] = defaultdict(int)

        def visit(nodes: tuple[ElementTerm | GroupTerm, ...], factor: int) -> None:
            for node in nodes:
                next_factor = factor * node.multiplier
                if next_factor > self.limits.max_total_atoms:
                    raise FormulaResourceLimitError(
                        "ATOM_LIMIT", self.position, "atom count exceeds limit"
                    )
                if isinstance(node, ElementTerm):
                    totals[node.symbol] += next_factor
                    if totals[node.symbol] > self.limits.max_total_atoms:
                        raise FormulaResourceLimitError(
                            "ATOM_LIMIT", self.position, "atom count exceeds limit"
                        )
                else:
                    visit(node.terms, next_factor)

        visit(terms, 1)
        if not totals:
            raise FormulaParseError("EMPTY_FORMULA", 0, "formula contains no elements")
        if len(totals) > self.limits.max_distinct_elements:
            raise FormulaResourceLimitError(
                "DISTINCT_ELEMENT_LIMIT",
                self.position,
                "distinct-element count exceeded",
            )
        if sum(totals.values()) > self.limits.max_total_atoms:
            raise FormulaResourceLimitError(
                "ATOM_LIMIT", self.position, "total atom count exceeds limit"
            )
        return tuple(
            CompositionEntry(symbol, totals[symbol]) for symbol in sorted(totals)
        )


def render_terms(terms: tuple[ElementTerm | GroupTerm, ...]) -> str:
    rendered = []
    for term in terms:
        if isinstance(term, ElementTerm):
            text = term.symbol
        else:
            text = f"({render_terms(term.terms)})"
        rendered.append(text + (str(term.multiplier) if term.multiplier != 1 else ""))
    return "".join(rendered)


def verify_ast(ast: FormulaAst) -> None:
    body = asdict(ast)
    digest = body.pop("ast_hash")
    if content_hash(body) != digest:
        raise ValueError("formula AST hash mismatch")
