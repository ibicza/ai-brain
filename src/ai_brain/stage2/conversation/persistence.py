"""Transactional checksummed conversation persistence."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.conversation.models import (
    ConversationIntent,
    ConversationState,
    ConversationTurn,
    PendingAction,
    PendingActionStatus,
    Speaker,
    TutorConversation,
)
from ai_brain.stage2.conversation.pending_actions import verify_pending
from ai_brain.stage2.conversation.state_machine import require_transition
from ai_brain.stage2.conversation.version import CONVERSATION_STORE_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)


class ConversationStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.database_path = self.root / "conversations.sqlite3"

    @classmethod
    def initialize(cls, root: Path) -> ConversationStore:
        store = cls(root)
        store.root.mkdir(parents=True, exist_ok=True)
        if store.database_path.exists():
            raise FileExistsError("conversation store already exists")
        with store._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY,learner_id TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,conversation_hash TEXT NOT NULL);
                CREATE TABLE turns(conversation_id TEXT NOT NULL,sequence INTEGER NOT NULL,turn_id TEXT UNIQUE NOT NULL,turn_hash TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,PRIMARY KEY(conversation_id,sequence),FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id));
                CREATE TABLE pending_actions(pending_id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,learner_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id));
                CREATE TABLE public_responses(turn_hash TEXT PRIMARY KEY,response_hash TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,FOREIGN KEY(turn_hash) REFERENCES turns(turn_hash));
                CREATE TABLE clarifications(clarification_id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id));
                CREATE TABLE audit_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id TEXT NOT NULL,kind TEXT NOT NULL,created_at TEXT NOT NULL,payload_hash TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id));
                """
            )
            connection.executemany(
                "INSERT INTO metadata VALUES(?,?)",
                (
                    ("schema_version", str(CONVERSATION_STORE_SCHEMA_VERSION)),
                    ("created_at", utc_now()),
                ),
            )
        return store

    @classmethod
    def open(cls, root: Path) -> ConversationStore:
        store = cls(root)
        if not store.database_path.is_file():
            raise FileNotFoundError("conversation database is missing")
        with store._connection() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
        if row is None or row[0] != str(CONVERSATION_STORE_SCHEMA_VERSION):
            raise ValueError("conversation store requires an explicit rebuild")
        return store

    @classmethod
    def open_or_initialize(cls, root: Path) -> ConversationStore:
        return (
            cls.open(root)
            if (root.resolve() / "conversations.sqlite3").exists()
            else cls.initialize(root)
        )

    def create(self, conversation: TutorConversation) -> None:
        _verify_conversation(conversation)
        payload = canonical_json(asdict(conversation))
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO conversations VALUES(?,?,?,?,?)",
                (
                    conversation.conversation_id,
                    conversation.learner_id,
                    payload,
                    bytes_hash(payload.encode()),
                    conversation.conversation_hash,
                ),
            )

    def get(self, conversation_id: str) -> TutorConversation:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload,payload_hash FROM conversations WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        if row is None or bytes_hash(row[0].encode()) != row[1]:
            raise KeyError("unknown or corrupt conversation")
        payload = json.loads(row[0])
        payload["state"] = ConversationState(payload["state"])
        payload["previous_active_state"] = ConversationState(
            payload["previous_active_state"]
        )
        payload["turn_hashes"] = tuple(payload["turn_hashes"])
        result = TutorConversation(**payload)
        _verify_conversation(result)
        return result

    def append_interaction(
        self,
        old: TutorConversation,
        new: TutorConversation,
        turn: ConversationTurn,
        response_payload: str,
        response_hash: str,
        pending_action: PendingAction | None = None,
    ) -> None:
        _verify_conversation(old)
        _verify_conversation(new)
        _verify_turn(turn)
        if new.turn_hashes != old.turn_hashes + (
            turn.turn_hash,
        ) or turn.previous_turn_hash != (
            old.turn_hashes[-1] if old.turn_hashes else None
        ):
            raise ValueError("turn does not extend the conversation")
        new_payload = canonical_json(asdict(new))
        turn_payload = canonical_json(asdict(turn))
        if pending_action is not None:
            verify_pending(pending_action)
            if (
                pending_action.conversation_id != old.conversation_id
                or new.pending_action_id != pending_action.pending_id
            ):
                raise ValueError("pending action does not bind the transition")
        with self._connection() as connection:
            current = connection.execute(
                "SELECT conversation_hash FROM conversations WHERE conversation_id=?",
                (old.conversation_id,),
            ).fetchone()
            if current is None or current[0] != old.conversation_hash:
                raise ValueError("stale conversation update")
            if pending_action is not None:
                pending_payload = canonical_json(asdict(pending_action))
                connection.execute(
                    "INSERT INTO pending_actions VALUES(?,?,?,?,?,?)",
                    (
                        pending_action.pending_id,
                        pending_action.conversation_id,
                        pending_action.learner_id,
                        pending_action.status.value,
                        pending_payload,
                        bytes_hash(pending_payload.encode()),
                    ),
                )
            connection.execute(
                "INSERT INTO turns VALUES(?,?,?,?,?,?)",
                (
                    turn.conversation_id,
                    turn.sequence,
                    turn.turn_id,
                    turn.turn_hash,
                    turn_payload,
                    bytes_hash(turn_payload.encode()),
                ),
            )
            connection.execute(
                "INSERT INTO public_responses VALUES(?,?,?,?)",
                (
                    turn.turn_hash,
                    response_hash,
                    response_payload,
                    bytes_hash(response_payload.encode()),
                ),
            )
            updated = connection.execute(
                "UPDATE conversations SET payload=?,payload_hash=?,conversation_hash=? WHERE conversation_id=? AND conversation_hash=?",
                (
                    new_payload,
                    bytes_hash(new_payload.encode()),
                    new.conversation_hash,
                    new.conversation_id,
                    old.conversation_hash,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("atomic conversation transition failed")
            connection.execute(
                "INSERT INTO audit_events(conversation_id,kind,created_at,payload_hash) VALUES(?,?,?,?)",
                (new.conversation_id, "TURN_APPENDED", turn.created_at, turn.turn_hash),
            )

    def turns(self, conversation_id: str) -> tuple[ConversationTurn, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload,payload_hash FROM turns WHERE conversation_id=? ORDER BY sequence",
                (conversation_id,),
            ).fetchall()
        result = []
        for payload, checksum in rows:
            if bytes_hash(payload.encode()) != checksum:
                raise ValueError("conversation turn checksum mismatch")
            row = json.loads(payload)
            row["speaker"] = Speaker(row["speaker"])
            row["parsed_intent"] = ConversationIntent(row["parsed_intent"])
            result.append(ConversationTurn(**row))
        return tuple(result)

    def save_pending(self, action: PendingAction) -> None:
        verify_pending(action)
        payload = canonical_json(asdict(action))
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO pending_actions VALUES(?,?,?,?,?,?)",
                (
                    action.pending_id,
                    action.conversation_id,
                    action.learner_id,
                    action.status.value,
                    payload,
                    bytes_hash(payload.encode()),
                ),
            )

    def get_pending(self, pending_id: str) -> PendingAction:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload,payload_hash FROM pending_actions WHERE pending_id=?",
                (pending_id,),
            ).fetchone()
        if row is None or bytes_hash(row[0].encode()) != row[1]:
            raise KeyError("unknown pending action")
        payload = json.loads(row[0])
        payload["dependency_snapshot"] = tuple(payload["dependency_snapshot"])
        payload["previous_state"] = ConversationState(payload["previous_state"])
        payload["status"] = PendingActionStatus(payload["status"])
        action = PendingAction(**payload)
        verify_pending(action)
        return action

    def replace_pending(self, old: PendingAction, new: PendingAction) -> None:
        verify_pending(new)
        payload = canonical_json(asdict(new))
        with self._connection() as connection:
            updated = connection.execute(
                "UPDATE pending_actions SET status=?,payload=?,payload_hash=? WHERE pending_id=? AND payload_hash=?",
                (
                    new.status.value,
                    payload,
                    bytes_hash(payload.encode()),
                    old.pending_id,
                    bytes_hash(canonical_json(asdict(old)).encode()),
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("pending action was already consumed")

    def verify(self) -> dict[str, object]:
        with self._connection() as connection:
            ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT conversation_id FROM conversations ORDER BY conversation_id"
                )
            )
        turn_count = 0
        for identity in ids:
            conversation = self.get(identity)
            turns = self.turns(identity)
            previous = None
            replayed_state = ConversationState.IDLE
            active_session_id = None
            for sequence, turn in enumerate(turns, 1):
                _verify_turn(turn)
                if turn.sequence != sequence or turn.previous_turn_hash != previous:
                    raise ValueError("invalid conversation turn chain")
                with self._connection() as connection:
                    response = connection.execute(
                        "SELECT response_hash,payload,payload_hash FROM public_responses WHERE turn_hash=?",
                        (turn.turn_hash,),
                    ).fetchone()
                if (
                    response is None
                    or bytes_hash(response[1].encode()) != response[2]
                    or content_hash(json.loads(response[1])) != response[0]
                    or turn.public_response_hash != response[0]
                ):
                    raise ValueError("invalid public response record")
                public = json.loads(response[1])
                if public.get("conversation_id") != identity:
                    raise ValueError("public response references another conversation")
                next_state = ConversationState(public.get("conversation_state"))
                if next_state != replayed_state:
                    require_transition(replayed_state, next_state)
                replayed_state = next_state
                exercise = public.get("exercise")
                if exercise is not None:
                    active_session_id = exercise["session"]["session_id"]
                previous = turn.turn_hash
            if conversation.turn_hashes != tuple(item.turn_hash for item in turns):
                raise ValueError("conversation turn index mismatch")
            if (
                conversation.state is not replayed_state
                or conversation.active_tutor_session_id != active_session_id
            ):
                raise ValueError(
                    "conversation state is not replayable from public turns"
                )
            turn_count += len(turns)
        return {
            "status": "VERIFIED",
            "conversation_count": len(ids),
            "turn_count": turn_count,
        }

    def conversation_ids(self) -> tuple[str, ...]:
        with self._connection() as connection:
            return tuple(
                row[0]
                for row in connection.execute(
                    "SELECT conversation_id FROM conversations ORDER BY conversation_id"
                )
            )

    def backup(self, output: Path) -> dict[str, object]:
        verification = self.verify()
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source, sqlite3.connect(output) as target:
            source.backup(target)
        return {
            **verification,
            "status": "BACKED_UP",
            "bytes_hash": bytes_hash(output.read_bytes()),
        }

    @classmethod
    def restore(cls, backup: Path, target_root: Path) -> ConversationStore:
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / "conversations.sqlite3"
        if target.exists():
            raise FileExistsError("conversation restore target exists")
        shutil.copyfile(backup, target)
        result = cls.open(target_root)
        result.verify()
        return result

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            with connection:
                yield connection
        finally:
            connection.close()


def _verify_conversation(value: TutorConversation) -> None:
    body = asdict(value)
    digest = body.pop("conversation_hash")
    if content_hash(body) != digest:
        raise ValueError("conversation hash mismatch")


def _verify_turn(value: ConversationTurn) -> None:
    body = asdict(value)
    digest = body.pop("turn_hash")
    if content_hash(body) != digest:
        raise ValueError("conversation turn hash mismatch")
