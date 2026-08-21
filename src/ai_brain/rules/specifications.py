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
    unsupported: bool = False

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
                f"unsupported={self.unsupported}",
            ]
        )
