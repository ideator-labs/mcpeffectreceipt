#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

reset_data() {
  rm -rf data
  mkdir -p data
  : > data/charges.log
}

count_charges() {
  if [[ -f data/charges.log ]]; then
    wc -l < data/charges.log | tr -d ' '
  else
    echo 0
  fi
}

call_py() {
  python3 - "$@" <<'PY'
import json, sys
from pathlib import Path
from server import Dispatch

msg = json.loads(sys.argv[1])
d = Dispatch(Path("data/ledger.sqlite"), Path("data/charges.log"))
try:
    out = d.handle(msg)
    print(json.dumps(out, sort_keys=True))
finally:
    d.close()
PY
}

pass_count=0
fail_count=0

echo "=== McpEffectReceipt demo ==="
echo

# PATH A: unguarded retry doubles the side effect
reset_data
echo "PATH A (unguarded): BEFORE charges=$(count_charges)"
r1=$(call_py '{"method":"tools/call","params":{"name":"charge","arguments":{"amount":10}}}')
r2=$(call_py '{"method":"tools/call","params":{"name":"charge","arguments":{"amount":10}}}')
a_lines=$(count_charges)
echo "PATH A AFTER first=$r1"
echo "PATH A AFTER second=$r2"
echo "PATH A AFTER charges=$a_lines"
if [[ "$a_lines" == "2" ]]; then
  echo "PATH A (unguarded): PASS"
  pass_count=$((pass_count + 1))
else
  echo "PATH A (unguarded): FAIL (expected 2 charge lines, got $a_lines)"
  fail_count=$((fail_count + 1))
fi
echo

# PATH B: guarded same key replays, one mutation
reset_data
echo "PATH B (guarded same key): BEFORE charges=$(count_charges)"
b1=$(call_py '{"method":"tools/call","params":{"name":"charge","arguments":{"amount":10},"idempotencyKey":"k1"}}')
b2=$(call_py '{"method":"tools/call","params":{"name":"charge","arguments":{"amount":10},"idempotencyKey":"k1"}}')
b_lines=$(count_charges)
echo "PATH B AFTER first=$b1"
echo "PATH B AFTER second=$b2"
echo "PATH B AFTER charges=$b_lines"
b1_mode=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["mode"])' "$b1")
b2_mode=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["mode"])' "$b2")
b1_tx=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["result"]["tx"])' "$b1")
b2_tx=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["result"]["tx"])' "$b2")
if [[ "$b_lines" == "1" && "$b1_mode" == "execute" && "$b2_mode" == "replay" && "$b1_tx" == "$b2_tx" ]]; then
  echo "PATH B (guarded same key): PASS"
  pass_count=$((pass_count + 1))
else
  echo "PATH B (guarded same key): FAIL (lines=$b_lines modes=$b1_mode/$b2_mode tx=$b1_tx/$b2_tx)"
  fail_count=$((fail_count + 1))
fi
echo

# PATH C: same key different args conflicts, no second mutation
reset_data
echo "PATH C (conflict): BEFORE charges=$(count_charges)"
c1=$(call_py '{"method":"tools/call","params":{"name":"charge","arguments":{"amount":10},"idempotencyKey":"k2"}}')
c2=$(call_py '{"method":"tools/call","params":{"name":"charge","arguments":{"amount":25},"idempotencyKey":"k2"}}')
c_lines=$(count_charges)
echo "PATH C AFTER first=$c1"
echo "PATH C AFTER second=$c2"
echo "PATH C AFTER charges=$c_lines"
c1_mode=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["mode"])' "$c1")
c2_mode=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["mode"])' "$c2")
c2_ok=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["ok"])' "$c2")
if [[ "$c_lines" == "1" && "$c1_mode" == "execute" && "$c2_mode" == "conflict" && "$c2_ok" == "False" ]]; then
  echo "PATH C (conflict): PASS"
  pass_count=$((pass_count + 1))
else
  echo "PATH C (conflict): FAIL (lines=$c_lines modes=$c1_mode/$c2_mode ok=$c2_ok)"
  fail_count=$((fail_count + 1))
fi
echo

echo "SUMMARY: $pass_count passed, $fail_count failed"
if [[ "$fail_count" -ne 0 || "$pass_count" -ne 3 ]]; then
  exit 1
fi
echo "ALL CLAIMS PASSED"
exit 0
