"""Dict dispatch shaped like MCP tools/call with optional params.idempotencyKey."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from charge import charge
from receipt import Conflict, InProgress, Ledger, Proceed, Replay


class Dispatch:
    def __init__(self, ledger_path: Path, charges_path: Path) -> None:
        self.ledger = Ledger(ledger_path)
        self.charges_path = Path(charges_path)

    def close(self) -> None:
        self.ledger.close()

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        if message.get("method") != "tools/call":
            return {"error": "unsupported method", "method": message.get("method")}
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name != "charge":
            return {"error": "unknown tool", "name": name}
        amount = arguments.get("amount")
        if not isinstance(amount, int):
            return {"error": "amount must be int"}

        key = params.get("idempotencyKey")
        if not key:
            result = charge(amount, self.charges_path)
            return {"ok": True, "mode": "unguarded", "result": result}

        outcome = self.ledger.begin(key, "charge", arguments)
        if isinstance(outcome, Proceed):
            result = charge(amount, self.charges_path)
            self.ledger.complete(key, result)
            return {"ok": True, "mode": "execute", "result": result}
        if isinstance(outcome, Replay):
            return {"ok": True, "mode": "replay", "result": outcome.receipt.result}
        if isinstance(outcome, Conflict):
            return {
                "ok": False,
                "mode": "conflict",
                "error": "idempotency key reused with different arguments",
                "stored_args_hash": outcome.receipt.args_hash,
            }
        if isinstance(outcome, InProgress):
            return {
                "ok": False,
                "mode": "in_progress",
                "error": "idempotency key already in progress",
            }
        raise RuntimeError(f"unhandled outcome {outcome!r}")
