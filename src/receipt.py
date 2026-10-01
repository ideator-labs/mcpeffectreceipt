"""EffectReceipt is the durable identity of one logical MCP tools/call mutation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


def hash_args(args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EffectReceipt:
    key: str
    tool: str
    args_hash: str
    status: Literal["in_progress", "completed", "conflict"]
    result: dict[str, Any] | None
    created_at: str


@dataclass(frozen=True)
class Proceed:
    receipt: EffectReceipt


@dataclass(frozen=True)
class Replay:
    receipt: EffectReceipt


@dataclass(frozen=True)
class Conflict:
    receipt: EffectReceipt


@dataclass(frozen=True)
class InProgress:
    receipt: EffectReceipt


BeginOutcome = Proceed | Replay | Conflict | InProgress


class Ledger:
    """SQLite write-ahead ledger for idempotencyKey dedup before side effects."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                key TEXT PRIMARY KEY,
                tool TEXT NOT NULL,
                args_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
                result_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def begin(self, key: str, tool: str, args: dict[str, Any]) -> BeginOutcome:
        args_hash = hash_args(args)
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute("SELECT key, tool, args_hash, status, result_json, created_at FROM receipts WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO receipts (key, tool, args_hash, status, result_json, created_at) VALUES (?, ?, ?, 'in_progress', NULL, ?)",
                (key, tool, args_hash, now),
            )
            self._conn.commit()
            receipt = EffectReceipt(key, tool, args_hash, "in_progress", None, now)
            return Proceed(receipt)

        stored_key, stored_tool, stored_hash, status, result_json, created_at = row
        result = json.loads(result_json) if result_json else None
        if stored_hash != args_hash or stored_tool != tool:
            view = EffectReceipt(stored_key, stored_tool, stored_hash, "conflict", result, created_at)
            return Conflict(view)
        if status == "completed":
            receipt = EffectReceipt(stored_key, stored_tool, stored_hash, "completed", result, created_at)
            return Replay(receipt)
        receipt = EffectReceipt(stored_key, stored_tool, stored_hash, "in_progress", result, created_at)
        return InProgress(receipt)

    def complete(self, key: str, result: dict[str, Any]) -> None:
        result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
        cur = self._conn.execute(
            "UPDATE receipts SET status = 'completed', result_json = ? WHERE key = ? AND status = 'in_progress'",
            (result_json, key),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"complete failed for key={key!r}: no in_progress row")
        self._conn.commit()
