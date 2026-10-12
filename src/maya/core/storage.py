"""Small transactional SQLite store for chats, explicit memories, feedback, and model cache."""

from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import re
import sqlite3
import time
from collections.abc import Iterator

from .types import MayaError, Message, Model
from .safety import redact


# --- Persistence: per-operation connections are safe across worker/UI threads. ---
class HistoryStore:
    """Local text persistence; screenshots and credentials are intentionally absent from its schema."""

    def __init__(self, path: Path):
        """Initialize a WAL database; interrupted generations are marked after a restart."""
        self.path = path
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
                    had_image INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id, id);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, scope TEXT NOT NULL,
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (
                    message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                    rating INTEGER NOT NULL CHECK(rating IN (-1,1)));
                CREATE TABLE IF NOT EXISTS catalog (
                    provider TEXT PRIMARY KEY, data TEXT NOT NULL, refreshed REAL NOT NULL,
                    identity TEXT NOT NULL DEFAULT '');
                PRAGMA user_version=1;
            """)
            db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Commit on success, rollback on error, and always release the connection."""
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_chat(self, title: str = "New conversation") -> int:
        """Create a chat lazily on first submitted turn and return its local ID."""
        with self.connection() as db:
            return int(
                db.execute(
                    "INSERT INTO chats(title,created) VALUES (?,?)", (title[:100], time.time())
                ).lastrowid
            )

    def chats(self, search: str = "") -> list[dict]:
        """Search titles and message text literally; SQL wildcard characters remain ordinary text."""
        query = search.strip()[:200].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM chats WHERE title LIKE ? ESCAPE '\\' OR EXISTS "
                    "(SELECT 1 FROM messages WHERE chat_id=chats.id AND text LIKE ? ESCAPE '\\') "
                    "ORDER BY id DESC LIMIT 200",
                    (f"%{query}%", f"%{query}%"),
                )
            ]

    def add_message(self, chat: int, message: Message, provider: str = "", model: str = "") -> int:
        """Insert text and an image-presence marker; binary images are never stored."""
        with self.connection() as db:
            return int(
                db.execute(
                    "INSERT INTO messages(chat_id,role,text,status,provider,model,had_image,created) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        chat,
                        message.role,
                        message.text,
                        message.status,
                        provider,
                        model,
                        bool(message.image),
                        time.time(),
                    ),
                ).lastrowid
            )

    def begin_turn(
        self,
        chat: int | None,
        user: Message,
        assistant: Message,
        provider: str,
        model: str,
        replace_from: int | None = None,
    ) -> tuple[int, int, int]:
        """Commit a complete pending turn in one transaction; a failed regenerate retains the old turn."""
        with self.connection() as db:
            if chat is None:
                chat = int(
                    db.execute(
                        "INSERT INTO chats(title,created) VALUES (?,?)", (user.text[:100], time.time())
                    ).lastrowid
                )
            if replace_from is not None:
                db.execute("DELETE FROM messages WHERE chat_id=? AND id>=?", (chat, replace_from))
            ids = []
            for message in (user, assistant):
                ids.append(
                    int(
                        db.execute(
                            "INSERT INTO messages(chat_id,role,text,status,provider,model,had_image,created) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                chat,
                                message.role,
                                message.text,
                                message.status,
                                provider,
                                model,
                                bool(message.image),
                                time.time(),
                            ),
                        ).lastrowid
                    )
                )
        return chat, ids[0], ids[1]

    def update_message(self, message: Message) -> None:
        """Persist an assistant's final/partial text or an edited user turn."""
        if message.id is not None:
            with self.connection() as db:
                db.execute(
                    "UPDATE messages SET text=?, status=? WHERE id=?",
                    (message.text, message.status, message.id),
                )

    def messages(self, chat: int) -> list[Message]:
        """Load the latest 300 turns in chronological order; image context must be attached again."""
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 300", (chat,)
            ).fetchall()
            return [Message(row["role"], row["text"], row["status"], row["id"]) for row in reversed(rows)]

    def truncate(self, chat: int, first_message: int) -> None:
        """Remove the replaced turn and following messages during an explicit regenerate/edit action."""
        with self.connection() as db:
            db.execute("DELETE FROM messages WHERE chat_id=? AND id>=?", (chat, first_message))

    def delete_chat(self, chat: int) -> None:
        """Delete one user-selected chat and its dependent messages/feedback transactionally."""
        with self.connection() as db:
            db.execute("DELETE FROM chats WHERE id=?", (chat,))

    def rename_chat(self, chat: int, title: str) -> None:
        """Rename a saved conversation without changing its messages or creation date."""
        title = title.strip()
        if not title or len(title) > 100:
            raise MayaError("A conversation title must contain 1–100 characters.", "validation")
        if redact(title)[1]:
            raise MayaError("Do not put recognizable credentials in a conversation title.", "privacy")
        with self.connection() as db:
            if not db.execute("UPDATE chats SET title=? WHERE id=?", (title, chat)).rowcount:
                raise MayaError("This conversation no longer exists. Refresh history.", "validation")

    def clear_chats(self) -> None:
        """Erase history on explicit user action, including dependent feedback."""
        with self.connection() as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM chats")
            db.commit()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def remember(self, text: str, scope: str = "general") -> None:
        """Save a user-approved preference/fact; duplicate memories are harmless."""
        text = self.validate_memory(text, scope)
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO memories(text,scope,created) VALUES(?,?,?)", (text, scope, time.time())
            )

    @staticmethod
    def validate_memory(text: str, scope: str) -> str:
        """Enforce memory bounds and secret rejection at the persistence boundary as well as the UI."""
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 1000:
            raise MayaError("A memory must contain 1–1,000 characters.", "validation")
        if not isinstance(scope, str) or not scope or len(scope) > 64:
            raise MayaError("Choose a valid memory scope.", "validation")
        if redact(text)[1]:
            raise MayaError("Do not store API keys, passwords, or tokens as memories.", "privacy")
        return text.strip()

    def update_memory(self, memory: int, text: str, scope: str) -> None:
        """Update one explicitly selected memory atomically; duplicates never overwrite another memory."""
        text = self.validate_memory(text, scope)
        try:
            with self.connection() as db:
                if not db.execute(
                    "UPDATE memories SET text=?, scope=? WHERE id=?", (text, scope, memory)
                ).rowcount:
                    raise MayaError("This memory no longer exists. Select another memory.", "validation")
        except sqlite3.IntegrityError as exc:
            raise MayaError(
                "That memory is already saved. Edit or forget the existing entry.", "validation"
            ) from exc

    def memories(self) -> list[dict]:
        """List at most 500 local memories for inspection and editing."""
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM memories ORDER BY id DESC LIMIT 500")]

    def forget(self, memory: int) -> None:
        """Remove a selected local memory; no remote memory exists in this application."""
        with self.connection() as db:
            db.execute("DELETE FROM memories WHERE id=?", (memory,))

    def clear_memories(self) -> None:
        """Forget every approved memory atomically, without deleting chats or credentials.

        Secure deletion clears removed SQLite records where possible. It cannot erase old backups,
        operating-system snapshots or memory already sent in an earlier provider request.
        """
        with self.connection() as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM memories")

    def relevant_memories(self, question: str, skill: str) -> list[str]:
        """Retrieve up to eight preferences with deterministic term/scope ranking, not invented facts."""
        terms = set(re.findall(r"\w+", question.casefold()))
        ranked = []
        for item in self.memories():
            if item["scope"] not in {"general", skill}:
                continue
            overlap = len(terms & set(re.findall(r"\w+", item["text"].casefold())))
            score = overlap + (2 if item["scope"] == skill else 1)
            ranked.append((score, item["id"], item["text"]))
        return [text for _, _, text in sorted(ranked, reverse=True)[:8]]

    def rate(self, message_id: int, rating: int) -> None:
        """Store local helpful/unhelpful feedback; it is not model training or an automatic memory."""
        if rating not in {-1, 1}:
            raise ValueError("rating must be -1 or 1")
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO feedback VALUES(?,?)", (message_id, rating))

    def cache_models(self, provider: str, models: list[Model], identity: str) -> None:
        """Cache public metadata scoped to an endpoint/key fingerprint so account changes invalidate it."""
        data = json.dumps([asdict(model) for model in models])
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO catalog VALUES(?,?,?,?)", (provider, data, time.time(), identity)
            )

    def cached_models(self, provider: str, identity: str, ttl: int = 3600) -> tuple[list[Model], float]:
        """Return only matching, fresh metadata; stale lists are refreshed explicitly."""
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM catalog WHERE provider=? AND identity=?", (provider, identity)
            ).fetchone()
        if not row or time.time() - row["refreshed"] > ttl:
            return [], 0
        try:
            models = [
                Model(**{**item, "parameters": tuple(item.get("parameters", []))})
                for item in json.loads(row["data"])
            ]
        except (ValueError, TypeError):
            return [], 0
        return models, row["refreshed"]
