"""Structured, target-free program specifications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramSpecification:
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    transfers: tuple[tuple[str, str], ...] = ()
    drops: tuple[str, ...] = ()
    preserve: tuple[str, ...] = ()
    terminate_when_empty: tuple[str, ...] = ()
    allowed_variables: tuple[str, ...] = ()
    allowed_primitives: tuple[str, ...] = ()
    phase_constraints: tuple[tuple[str, str, str | None], ...] = ()
    unsupported: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "inputs",
            "outputs",
            "drops",
            "preserve",
            "terminate_when_empty",
            "allowed_variables",
            "allowed_primitives",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(
            self, "transfers", tuple(tuple(item) for item in self.transfers)
        )
        object.__setattr__(
            self,
            "phase_constraints",
            tuple(
                (str(item[0]), str(item[1]), item[2]) for item in self.phase_constraints
            ),
        )

    def roles(self) -> tuple[str, ...]:
        roles = set(self.inputs) | set(self.outputs) | set(self.drops)
        for source, destination in self.transfers:
            roles.add(source)
            roles.add(destination)
        roles.update(self.preserve)
        roles.update(self.terminate_when_empty)
        return tuple(sorted(roles))

    def is_full(self) -> bool:
        return bool(
            self.transfers
            or self.drops
            or self.preserve
            or self.terminate_when_empty
            or self.allowed_variables
            or self.allowed_primitives
            or self.phase_constraints
            or self.unsupported
        )

    def to_model_text(self) -> str:
        return " ".join(
            [
                f"inputs={self.inputs}",
                f"outputs={self.outputs}",
                f"transfers={self.transfers}",
                f"drops={self.drops}",
                f"preserve={self.preserve}",
                f"terminate={self.terminate_when_empty}",
                f"variables={self.allowed_variables}",
                f"primitives={self.allowed_primitives}",
                f"phases={self.phase_constraints}",
                f"unsupported={self.unsupported}",
            ]
        )
