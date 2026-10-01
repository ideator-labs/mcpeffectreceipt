# McpEffectReceipt

Agents and contributors, read [AGENTS.md](AGENTS.md) before you change anything.

## What it proves

A side-effecting MCP-style `tools/call` with a durable `idempotencyKey` ledger does not double-execute on retry.

- Unguarded retry (no key) runs the side effect twice.
- Same key and same args replay the stored receipt. One mutation.
- Same key and different args return conflict. No second mutation.

## Run

Needs Python 3.10+. Stdlib only.

```bash
bash demo.sh
```

Exit 0 means all three paths passed. Exit non-zero means a claim failed.

## Data shape

`EffectReceipt` in `src/receipt.py` is the durable row:

- `key`: client `idempotencyKey`
- `tool`: tool name (`charge`)
- `args_hash`: SHA-256 of canonical JSON args
- `status`: `in_progress` or `completed` in SQLite (`conflict` is an in-memory view only)
- `result`: stored tool result when completed
- `created_at`: ISO timestamp

`Ledger.begin` persists `in_progress` before the side effect runs. `Ledger.complete` attaches the result.

## Wire shape

Simulated MCP call (not an SDK server):

```json
{"method":"tools/call","params":{"name":"charge","arguments":{"amount":10},"idempotencyKey":"k1"}}
```

Omit `idempotencyKey` for the unguarded path.

## Limits

- Dict dispatch only. No MCP SDK, no real network transport.
- Single-process SQLite. No multi-worker lock stress in the demo.
- Fake `charge` appends to `data/charges.log`. Not a real payment API.
- Retention windows and provider-native tokens are out of scope.

## Sources

- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182
- https://eunomia.dev/research/agent-tool-retry-effect-idempotency/
- https://formation.dev/blog/agent-tool-retry-idempotency
- https://www.langchain.com/blog/mcp-in-langchain-stateless-protocol-elicitation-and-more
- https://github.com/azender1/SafeAgent
