#!/usr/bin/env python3
"""Stage 2 memory reader — pass-first + filtered-failure strategy.
Reads params from /tmp/sil-task-env (set by sil-setup.py).
Shows:
  1. All past PASSES (newest first) — the agent builds on success
  2. Failures ONLY if confidence >= 0.8 AND at least one pass exists
  3. If no passes: returns "No prior successful attempts"

Writes to stdout (for prompt injection) AND /tmp/sil-memory.txt.
"""
import sqlite3, sys, os

# Read params from env file
env = {}
for line in open("/tmp/sil-task-env"):
    if "=" in line:
        k, v = line.strip().split("=", 1)
        env[k] = v

DB_PATH = os.path.expanduser(env.get("experience_db", ""))
SIGNATURE = env.get("signature", "")
TASK_ID = env.get("task_id", "unknown")

if not DB_PATH or not SIGNATURE:
    print(f"MEMORY_HITS=0\nERROR: missing params (db={DB_PATH}, sig={SIGNATURE})")
    with open("/tmp/sil-memory.txt", "w") as f:
        f.write("MEMORY_HITS=0\nNo prior data.")
    sys.exit(0)

db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

rows = db.execute("""
    SELECT approach_tried, outcome, verdict, why, confidence, run_number, timestamp
    FROM experience
    WHERE problem_signature = ?
    ORDER BY run_number DESC, id DESC
""", (SIGNATURE,)).fetchall()

db.close()

passes = [r for r in rows if r["outcome"] == "pass"]
failures = [r for r in rows if r["outcome"] == "fail"]

output_parts = []

if not rows:
    output_parts.append("MEMORY_HITS=0\nNo prior attempts for this task.")
else:
    output_parts.append(f"MEMORY_HITS={len(rows)}")
    
    # ALWAYS show passes
    if passes:
        output_parts.append(f"\n## Past SUCCESSFUL attempts ({len(passes)}):")
        for i, r in enumerate(passes[:5], 1):
            output_parts.append(f"\n### Success #{i} (Run {r['run_number']})")
            output_parts.append(f"**Approach:**\n{r['approach_tried'][:500]}")
            if r["why"]:
                output_parts.append(f"**Why it worked:** {r['why'][:200]}")
    
    # Show failures ONLY if confidence >= 0.8 AND a pass exists
    has_pass = len(passes) > 0
    high_conf_failures = [r for r in failures if r["confidence"] >= 0.8]
    
    if high_conf_failures and has_pass:
        output_parts.append(f"\n## Past FAILED attempts WITH lessons ({len(high_conf_failures)}):")
        for i, r in enumerate(high_conf_failures[:3], 1):
            output_parts.append(f"\n### Failure #{i} (Run {r['run_number']}, confidence: {r['confidence']:.1f})")
            output_parts.append(f"**What was tried:**\n{r['approach_tried'][:300]}")
            output_parts.append(f"**Why it failed:** {r['why'][:200]}")
    elif failures and not has_pass:
        output_parts.append(f"\n## {len(failures)} past failures exist but no passes yet — solving cold")
        output_parts.append("(Failures without successes to contrast against are not shown to avoid poisoning.)")

output = "\n".join(output_parts)

print(output)
with open("/tmp/sil-memory.txt", "w") as f:
    f.write(output)
