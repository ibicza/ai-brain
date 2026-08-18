from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

WorkspaceOp = Literal["add", "sub"]


@dataclass(frozen=True)
class WorkspaceState:
    op: WorkspaceOp
    a: int
    b: int

    @property
    def result(self) -> int:
        return self.a + self.b if self.op == "add" else self.a - self.b

    @property
    def op_token(self) -> str:
        return "<OP_ADD>" if self.op == "add" else "<OP_SUB>"


def serialize_workspace_state(state: WorkspaceState) -> str:
    return "\n".join(
        (
            "<WS>",
            state.op_token,
            f"<A> {state.a}",
            f"<B> {state.b}",
            "</WS>",
        )
    )


def parse_workspace_state(text: str) -> WorkspaceState | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None

    op: WorkspaceOp | None = None
    a: int | None = None
    b: int | None = None
    for line in lines:
        if line == "<OP_ADD>":
            op = "add"
        elif line == "<OP_SUB>":
            op = "sub"
        elif match := re.fullmatch(r"<A>\s+(-?\d+)", line):
            a = int(match.group(1))
        elif match := re.fullmatch(r"<B>\s+(-?\d+)", line):
            b = int(match.group(1))

    if op is None or a is None or b is None:
        return None
    return WorkspaceState(op=op, a=a, b=b)


def workspace_slot_scores(
    *,
    expected: WorkspaceState,
    predicted: WorkspaceState | None,
) -> dict[str, bool]:
    return {
        "op_exact": predicted is not None and predicted.op == expected.op,
        "a_exact": predicted is not None and predicted.a == expected.a,
        "b_exact": predicted is not None and predicted.b == expected.b,
        "workspace_exact": predicted == expected,
    }


def canonical_workspace_answer(op: WorkspaceOp, a: int, b: int) -> str:
    return serialize_workspace_state(WorkspaceState(op=op, a=a, b=b))
