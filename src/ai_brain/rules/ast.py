"""Typed rule AST compatibility layer.

M-22.2 keeps the M-21 runtime semantics frozen.  The production package exposes
those typed objects from one import location while the implementation is still
backed by the already-tested M-21 script classes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
M21_PATH = ROOT / "scripts" / "m21_hybrid_neural_compiler_interpreter.py"


def _load_m21() -> Any:
    module_name = "m21_hybrid_neural_compiler_interpreter"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, M21_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {M21_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


m21 = _load_m21()

ProgramAst = m21.ProgramAst
ClauseAst = m21.ClauseAst
PredicateAst = m21.PredicateAst
ActionAst = m21.ActionAst
BindingAst = m21.BindingAst
RegisterState = m21.RegisterState
PhysicalAction = m21.PhysicalAction
REGISTERS = tuple(m21.REGISTERS)
LOGICAL_VARS = ("A", "B", "C", "D")
REG_BINDING = {"A": "R0", "B": "R1", "C": "R2", "D": "R3"}


def default_binding() -> BindingAst:
    return BindingAst(dict(REG_BINDING))


def render_canonical_program(
    program: ProgramAst, binding: BindingAst | None = None
) -> str:
    return m21.render_canonical_program(program, binding or default_binding())


def parse_canonical_dsl(text: str) -> tuple[ProgramAst, BindingAst]:
    return m21.parse_canonical_dsl(text)


def exact_closed_loop(
    program: ProgramAst, state: RegisterState, binding: BindingAst | None = None
) -> dict[str, Any]:
    return m21.exact_closed_loop(program, binding or default_binding(), state)


def verify_m21_program(program: ProgramAst, binding: BindingAst | None = None) -> None:
    m21.verify_program(program, binding or default_binding())


def stable_hash(text: str) -> str:
    return m21.stable_hash(text)


def program_variables(program: ProgramAst) -> set[str]:
    return m21.program_variables(program)


def make_program(clauses: list[ClauseAst], name: str = "program") -> ProgramAst:
    program = ProgramAst(tuple(clauses), name)
    program.validate(LOGICAL_VARS)
    return program
