# AGENTS.md - McpEffectReceipt

Cold-start handoff for a coding agent with no prior context.

## Claim proved

A mutating MCP-style `tools/call` that carries `params.idempotencyKey` and checks a durable ledger before dispatch does not double-execute on retry.

Evidence from `bash demo.sh`:

1. PATH A: two unguarded `charge(10)` calls produce 2 lines in `data/charges.log`.
2. PATH B: two guarded calls with key `k1` and amount 10 produce 1 line. Second response mode is `replay` with the same `tx`.
3. PATH C: key `k2` with amount 10 then amount 25 produces 1 line. Second response mode is `conflict`.

## Status: real vs stubbed

Real:

- `EffectReceipt` + SQLite `Ledger` write-ahead (`begin` then side effect then `complete`)
- Fake `charge` side effect (append to log)
- Dict dispatch matching SEP-3182 field placement (`idempotencyKey` sibling of `arguments`)
- Self-proving `demo.sh` with exit codes

Stubbed / not built:

- Live MCP SDK server or client
- Multi-process / multi-worker concurrency stress
- Retention TTL pruning
- Downstream provider idempotency token mapping (Stripe/AWS)
- Workflow Core or Hivemind integration

## Data shape (with paths)

Primary type: `EffectReceipt` in `src/receipt.py`.

| Field | Meaning |
| --- | --- |
| `key` | `idempotencyKey` |
| `tool` | tool name |
| `args_hash` | SHA-256 of `json.dumps(args, sort_keys=True, separators=(",", ":"))` |
| `status` | persisted: `in_progress` \| `completed`; view-only: `conflict` |
| `result` | tool result dict when completed |
| `created_at` | ISO-8601 UTC |

Begin outcomes (also in `src/receipt.py`): `Proceed`, `Replay`, `Conflict`, `InProgress`.

Durable store: `data/ledger.sqlite` (created at runtime).
Side-effect oracle: `data/charges.log` (one line per real charge).

## Repo map

| Path | Role |
| --- | --- |
| `src/receipt.py` | `EffectReceipt`, hash, ledger |
| `src/charge.py` | key-blind fake charge |
| `src/server.py` | `tools/call` dict dispatch |
| `src/__init__.py` | package marker |
| `demo.sh` | proof runner |
| `README.md` | short human summary |
| `AGENTS.md` | this file |
| `requirements.txt` | notes stdlib-only |
| `.gitignore` | ignores `data/`, caches |
| `LICENSE` | MIT |

## Setup / run / verify (fresh clone)

```bash
git clone https://github.com/ideator-labs/mcpeffectreceipt.git
cd mcpeffectreceipt
bash demo.sh
```

Needs Python 3.10+ on PATH. No pip install.

Expected pass (abridged):

```
PATH A (unguarded): PASS
PATH B (guarded same key): PASS
PATH C (conflict): PASS
SUMMARY: 3 passed, 0 failed
ALL CLAIMS PASSED
```

Exit code 0.

What failure looks like:

- Wrong line counts print `FAIL` for that path and exit 1.
- Example: if replay still appended, PATH B fails with `lines=2`.
- Example: if conflict still charged, PATH C fails with `lines=2`.

## Design decisions

1. **Sum-type begin outcomes.** `Proceed` vs `InProgress` cannot share one `status=in_progress` return without losing who owns the claim.
2. **Write-ahead before mutate.** `begin` COMMITs `in_progress` before `charge` opens the log.
3. **Charge stays key-blind.** Dedup lives in dispatch, matching protocol middleware rather than per-tool hacks.
4. **Conflict is not persisted.** Stored row stays as first write. Conflict is an in-memory view so a bad retry cannot overwrite a good receipt.
5. **No MCP SDK.** Wire-shaped dicts are enough to prove the claim today.

## Known limits

- Not a production MCP server.
- SQLite single writer; demo does not race two processes.
- No retention window; keys live until DB delete.
- Fake charge only; does not prove Stripe/AWS token handoff.
- `InProgress` is implemented but not exercised by a concurrent race in `demo.sh`.

## Prioritized next steps (done-when)

1. **Wire a real MCP server** that advertises `tools.idempotency` and reads `params.idempotencyKey` before tool handlers.
   - Done when: an MCP inspector or stdio client can run PATH B/C against the server and `demo.sh`-equivalent assertions pass.
2. **Multi-process lock test.**
   - Done when: two processes call the same key at once; exactly one executes; the other gets `in_progress` or `replay`; charge log has one line.
3. **Workflow Core ledger backend.**
   - Done when: `Ledger` persists via Workflow Core / SQLite provider and PATH B still passes after process restart between `begin` and `complete` recovery.
4. **Retention TTL.**
   - Done when: expired keys allow a new execute; documented clock control in demo proves it.

## Working rules

- Name data shape changes in `src/receipt.py` first.
- Keep `charge.py` free of idempotency logic.
- `bash demo.sh` must stay green. Do not publish a red demo.
- No em-dashes in prose.
- Prefer deleting abstractions over adding layers.

## Sources (checked URLs)

- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182
- https://eunomia.dev/research/agent-tool-retry-effect-idempotency/
- https://formation.dev/blog/agent-tool-retry-idempotency
- https://www.langchain.com/blog/mcp-in-langchain-stateless-protocol-elicitation-and-more
- https://github.com/azender1/SafeAgent
