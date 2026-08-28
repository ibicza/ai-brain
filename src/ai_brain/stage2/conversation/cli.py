"""CLI command registration and public-only dispatch for conversation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.conversation.persistence import ConversationStore
from ai_brain.stage2.conversation.replay import replay_conversation
from ai_brain.stage2.conversation.service import ConversationalTutorService
from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.progress.persistence import LearnerProgressStore

DEFAULT_CONVERSATIONS = Path("artifacts/education/m30/conversations")
DEFAULT_PROGRESS = Path("artifacts/education/m30/progress")


def add_chat_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--conversation-store", type=Path, default=DEFAULT_CONVERSATIONS
    )
    parser.add_argument("--progress-store", type=Path, default=DEFAULT_PROGRESS)


def add_chat_commands(commands) -> None:
    start = commands.add_parser("chat-start")
    start.add_argument("--learner", required=True)
    start.add_argument("--language", choices=("ru", "en"), default="ru")
    start.add_argument("--conversation")
    turn = commands.add_parser("chat-turn")
    turn.add_argument("--conversation", required=True)
    turn.add_argument("--text", required=True)
    confirm = commands.add_parser("chat-confirm")
    confirm.add_argument("--conversation", required=True)
    confirm.add_argument("--pending", required=True)
    cancel = commands.add_parser("chat-cancel")
    cancel.add_argument("--conversation", required=True)
    cancel.add_argument("--pending", required=True)
    progress = commands.add_parser("chat-progress")
    progress.add_argument("--conversation", required=True)
    export = commands.add_parser("chat-export-progress")
    export.add_argument("--learner", required=True)
    reset = commands.add_parser("chat-reset-progress")
    reset.add_argument("--learner", required=True)
    reset.add_argument("--confirm", action="store_true")
    delete = commands.add_parser("chat-delete-progress")
    delete.add_argument("--learner", required=True)
    delete.add_argument("--confirm", action="store_true")
    replay = commands.add_parser("chat-replay")
    replay.add_argument("--conversation", required=True)
    backup = commands.add_parser("chat-backup")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("chat-restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--target", type=Path, required=True)
    restore.add_argument("--kind", choices=("conversation", "progress"), required=True)


def dispatch_chat(args, education):
    if args.command == "chat-restore":
        store = (
            ConversationStore.restore(args.backup, args.target)
            if args.kind == "conversation"
            else LearnerProgressStore.restore(args.backup, args.target)
        )
        return store.verify()
    service = ConversationalTutorService.open(
        education, args.conversation_store, args.progress_store
    )
    if args.command == "chat-start":
        return service.start(
            args.learner, language=args.language, conversation_id=args.conversation
        )
    if args.command == "chat-turn":
        return service.turn(args.conversation, args.text)
    if args.command == "chat-confirm":
        return service.confirm(args.conversation, args.pending)
    if args.command == "chat-cancel":
        return service.cancel(args.conversation, args.pending)
    if args.command == "chat-progress":
        return service.progress_summary(args.conversation)
    if args.command == "chat-export-progress":
        return json.loads(service.export_progress(args.learner))
    if args.command == "chat-reset-progress":
        return service.reset_progress(args.learner, confirmed=args.confirm)
    if args.command == "chat-delete-progress":
        return service.delete_progress(args.learner, confirmed=args.confirm)
    if args.command == "chat-replay":
        return replay_conversation(service, args.conversation)
    if args.command == "chat-backup":
        return {
            "conversation": service.conversations.backup(
                args.output / "conversations.sqlite3"
            ),
            "progress": service.progress.backup(
                args.output / "learner_progress.sqlite3"
            ),
        }
    raise ValueError("unknown chat command")


def public_json(value) -> str:
    return canonical_json(
        asdict(value) if hasattr(value, "__dataclass_fields__") else value
    )
