"""Command-line interface for the trusted deterministic tutoring layer."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2.education.models import (
    ExerciseFamily,
    ExplanationMode,
    HintLevel,
)
from ai_brain.stage2.education.persistence import EducationalSessionStore
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import canonical_json

DEFAULT_CHEMISTRY_ROOT = Path("artifacts/domains/chemistry/m29")
DEFAULT_STORE_ROOT = Path("artifacts/education/m29")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-brain-tutor")
    parser.add_argument("--chemistry-root", type=Path, default=DEFAULT_CHEMISTRY_ROOT)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    explain = commands.add_parser("explain")
    explain.add_argument("--domain", choices=("chemistry",), default="chemistry")
    explain.add_argument("--language", choices=("ru", "en"), required=True)
    explain.add_argument("--request", type=Path, required=True)
    explain.add_argument(
        "--mode", choices=tuple(item.value for item in ExplanationMode), default="FULL"
    )

    generate = commands.add_parser("generate-exercise")
    generate.add_argument(
        "--family",
        choices=tuple(item.value.casefold() for item in ExerciseFamily),
        required=True,
    )
    generate.add_argument("--difficulty", type=int)
    generate.add_argument("--language", choices=("ru", "en"), required=True)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--session")

    submit = commands.add_parser("submit-answer")
    submit.add_argument("--session", required=True)
    submit.add_argument("--answer", required=True)
    submit.add_argument("--confirmed", action="store_true")

    hint = commands.add_parser("hint")
    hint.add_argument("--session", required=True)
    hint.add_argument("--level", type=int, choices=(1, 2, 3, 4, 5))

    solution = commands.add_parser("show-solution")
    solution.add_argument("--session", required=True)

    replay = commands.add_parser("replay")
    replay.add_argument("--session", required=True)

    commands.add_parser("verify")
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--target", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "restore":
        restored = EducationalSessionStore.restore(args.backup, args.target)
        _print(restored.verify())
        return
    service = EducationalService.open(args.chemistry_root, args.store)
    if args.command == "explain":
        request = _read_request(args.request)
        result, graph, explanation = service.explain_tool(
            request["tool_id"],
            request["arguments"],
            language=args.language,
            mode=ExplanationMode(args.mode),
        )
        _print(
            {
                "text": explanation.text,
                "explanation_hash": explanation.explanation_hash,
                "graph_hash": graph.graph_hash,
                "source_result_hash": result["result_hash"],
            }
        )
    elif args.command == "generate-exercise":
        _, instance, _, session = service.create_exercise(
            ExerciseFamily(args.family.upper()),
            seed=args.seed,
            language=args.language,
            difficulty=args.difficulty,
            session_id=args.session,
        )
        _print(
            {
                "session_id": session.session_id,
                "exercise_id": instance.instance_id,
                "question": instance.question_text,
                "language": instance.language,
                "difficulty": instance.difficulty_metadata,
            }
        )
    elif args.command == "submit-answer":
        answer, grade, session = service.submit_answer(
            args.session, args.answer, confirmed=args.confirmed
        )
        _print(
            {
                "parse_status": answer.parse_status,
                "status": grade.correctness_status,
                "score": grade.score,
                "diagnoses": tuple(item.code for item in grade.error_diagnoses),
                "session_status": session.status,
                "grading_result_hash": grade.result_hash,
            }
        )
    elif args.command == "hint":
        hint, session = service.hint(
            args.session, level=HintLevel(args.level) if args.level else None
        )
        _print(
            {
                "level": hint.level,
                "text": hint.text,
                "hint_hash": hint.hint_hash,
                "session_status": session.status,
            }
        )
    elif args.command == "show-solution":
        explanation, session = service.show_solution(args.session)
        _print(
            {
                "text": explanation.text,
                "explanation_hash": explanation.explanation_hash,
                "session_status": session.status,
            }
        )
    elif args.command == "replay":
        _print(service.replay(args.session))
    elif args.command == "verify":
        _print(service.verify())
    elif args.command == "backup":
        _print(service.store.backup(args.output))


def _read_request(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 16_384:
        raise ValueError("educational request file is too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"tool_id", "arguments"}
        or not isinstance(value["tool_id"], str)
        or not isinstance(value["arguments"], dict)
    ):
        raise ValueError("educational request has an invalid schema")
    return value


def _print(value: Any) -> None:
    print(
        canonical_json(
            asdict(value) if hasattr(value, "__dataclass_fields__") else value
        )
    )


if __name__ == "__main__":
    main()
