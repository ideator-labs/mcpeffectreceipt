"""Fake charge side effect. Key-blind on purpose. Mutation is one append."""

from __future__ import annotations

from pathlib import Path


def charge(amount: int, log_path: Path) -> dict:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        n = sum(1 for _ in log_path.open()) + 1
    else:
        n = 1
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"tx={n} amount={amount}\n")
    return {"charged": amount, "tx": n}
