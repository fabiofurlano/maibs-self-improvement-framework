#!/usr/bin/env python3.10
"""Proof runner — Condition B2 (REASONING LIFELINE).
For tasks that failed in BOTH condition A and B:
  1. Call DeepSeek V4 Pro with the problem + both failed attempts
  2. Get the reasoning chain back
  3. Inject reasoning into MiniMax M3's next attempt
Tasks that already passed in B are counted as-is.
Usage: python3.10 proof-run-reasoning.py
Output: ~/.hermes/planning/self-improvement-loop/results/proof-B2.json
"""
import json, os, sys, time, subprocess, sqlite3
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
RESULTS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/results")
OUTPUT_FILE = os.path.join(RESULTS_DIR, "proof-B2.json")

RUN_NUMBER = 4  # B2 = reasoning lifeline

task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
print(f"=== PROOF RUN {RUN_NUMBER} — CONDITION B2: REASONING LIFELINE ===")
print(f"  Tasks: {len(task_ids)}")
print(f"  Logic: if A=FAIL and B=FAIL → DeepSeek V4 Pro reasoning → M3 re-attempt")
print(f"  If B already PASS: skip, count as pass")
print()

passes = 0
fails = 0
lifeline_count = 0
skip_count = 0
results = []
start_time = time.time()

db = sqlite3.connect(DB_PATH)

for i, task_id in enumerate(task_ids, 1):
    task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
    task = json.load(open(task_file))

    # Check Run 2 (B) verdict
    b_row = db.execute(
        "SELECT verdict, approach_tried, why FROM experience WHERE task_id=? AND run_number=2",
        (task_id,)
    ).fetchone()

    if b_row and b_row[0] == 'pass':
        # Already passed in B — count as pass, no lifeline needed
        passes += 1
        skip_count += 1
        print(f"  [{i}/{len(task_ids)}] {task_id} ✅ (already passed in B, skipping)")
        results.append({
            "task_id": task_id,
            "condition": "B2",
            "run_number": RUN_NUMBER,
            "verdict": "PASS",
            "error": "",
            "lifeline_used": False,
            "note": "passed in condition B, no lifeline needed",
        })
        continue

    # Failed in B — check Run 1 (A)
    a_row = db.execute(
        "SELECT approach_tried, why FROM experience WHERE task_id=? AND run_number=1",
        (task_id,)
    ).fetchone()

    if not a_row:
        print(f"  [{i}/{len(task_id)}] {task_id} ❌ (no Run 1 data)")
        fails += 1
        continue

    # Both failed — REASONING LIFELINE
    lifeline_count += 1
    a_code = (a_row[0] or "")[:500]
    a_error = a_row[1] or "unknown"
    b_code = (b_row[1] or "")[:500] if b_row else ""
    b_error = (b_row[2] or "unknown") if b_row else "unknown"

    print(f"  [{i}/{len(task_ids)}] {task_id} 🧠 reasoning lifeline...", end="", flush=True)

    # === STEP 1: Call DeepSeek V4 Pro for reasoning ===
    deepseek_prompt = f"""You are a coding expert helping a weaker model solve a Python problem.

PROBLEM:
{task['prompt']}

The weaker model attempted this problem twice and failed both times.

ATTEMPT 1 (FAILED):
```python
{a_code}
```
Error: {a_error}

ATTEMPT 2 (FAILED):
```python
{b_code}
```
Error: {b_error}

Analyze both attempts. Identify WHY each one failed. Then explain the CORRECT approach. Finally, write the correct solution as a Python function in a markdown code block.

Your response format:
## Analysis
(why each attempt failed)

## Correct Approach
(what the right solution looks like)

## Solution
```python
(the correct function code)
```"""

    ds_start = time.time()
    try:
        ds_result = subprocess.run(
            ["hermes", "-z", deepseek_prompt, "-m", "deepseek-v4-pro", "--provider", "opencode-go"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": os.path.expanduser("~")}
        )
        deepseek_output = ds_result.stdout
        ds_elapsed = time.time() - ds_start
    except subprocess.TimeoutExpired:
        deepseek_output = ""
        ds_elapsed = 120
    except Exception as e:
        deepseek_output = f"ERROR: {e}"
        ds_elapsed = time.time() - ds_start

    # Extract the solution code from DeepSeek's response
    ds_lines = deepseek_output.split("\n")
    ds_in_block = False
    ds_code_lines = []
    ds_in_solution = False
    for line in ds_lines:
        stripped = line.strip()
        if "## Solution" in stripped:
            ds_in_solution = True
            continue
        if ds_in_solution and stripped.startswith("```"):
            if ds_in_block:
                break
            ds_in_block = True
            continue
        if ds_in_block and ds_in_solution:
            ds_code_lines.append(line)
    deepseek_code = "\n".join(ds_code_lines) if ds_code_lines else ""

    # === STEP 2: Build enriched prompt for M3 ===
    # Keep the failure memory (from B) + add DeepSeek's reasoning
    reasoning_summary = deepseek_output[:1500]  # Trim to avoid token bloat

    m3_prompt = f"""A stronger model analyzed your previous failures on this problem. Study its reasoning, then write the correct solution.

PROBLEM:
{task['prompt']}

EXPERT ANALYSIS OF YOUR PAST FAILURES:
{reasoning_summary}

---
Now write the CORRECT Python function. Return ONLY the function code in a single markdown code block.

```python
# Your corrected solution here
```"""

    m3_start = time.time()
    try:
        m3_result = subprocess.run(
            ["hermes", "-z", m3_prompt, "-m", "MiniMax-M3", "--provider", "minimax"],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "HOME": os.path.expanduser("~")}
        )
        m3_output = m3_result.stdout
        m3_elapsed = time.time() - m3_start
    except subprocess.TimeoutExpired:
        m3_output = ""
        m3_elapsed = 180
    except Exception as e:
        m3_output = f"ERROR: {e}"
        m3_elapsed = time.time() - m3_start

    total_elapsed = ds_elapsed + m3_elapsed

    # Extract code from M3 output
    m3_lines = m3_output.split("\n")
    m3_in_block = False
    m3_code_lines = []
    for line in m3_lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            m3_in_block = not m3_in_block
            continue
        if m3_in_block:
            m3_code_lines.append(line)
    m3_code = "\n".join(m3_code_lines) if m3_code_lines else m3_output

    # === STEP 3: Run oracle ===
    test_setup = task.get("test_setup_code", "")
    test_list = task["test_list"]
    full_code = (test_setup or "") + "\n" + m3_code + "\n" + "\n".join(test_list)

    try:
        exec(full_code, {})
        verdict = "PASS"
        error_msg = ""
    except AssertionError as e:
        verdict = "FAIL"
        error_msg = f"AssertionError: {str(e)[:200]}"
    except SyntaxError as e:
        verdict = "FAIL"
        error_msg = f"SyntaxError: {str(e)[:200]}"
    except Exception as e:
        verdict = "FAIL"
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"

    if verdict == "PASS":
        passes += 1
        status = "✅"
    else:
        fails += 1
        status = "❌"

    flip_from_b = (b_row and b_row[0] == 'fail' and verdict == "PASS")
    flip_marker = " 🔄 B→B2 FLIP!" if flip_from_b else ""
    err_short = f" ({error_msg[:60]})" if error_msg else ""
    print(f" {status}{flip_marker} (DS:{ds_elapsed:.1f}s + M3:{m3_elapsed:.1f}s){err_short}")

    # Record in DB for future reference
    db.execute(
        "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id[:16], task_id, "retry", m3_output[:500], verdict.lower(), verdict.lower(), error_msg, time.time(), 1.0, RUN_NUMBER)
    )
    db.commit()

    results.append({
        "task_id": task_id,
        "condition": "B2",
        "run_number": RUN_NUMBER,
        "verdict": verdict,
        "error": error_msg,
        "lifeline_used": True,
        "ds_time_s": round(ds_elapsed, 1),
        "m3_time_s": round(m3_elapsed, 1),
        "deepseek_output_trimmed": deepseek_output[:300] if deepseek_code else "",
    })

db.close()

# Save results
total_elapsed = time.time() - start_time
summary = {
    "condition": "B2 (reasoning lifeline — DeepSeek V4 Pro for double-fail tasks)",
    "model": "MiniMax-M3 + DeepSeek V4 Pro (lifeline)",
    "provider": "minimax + opencode-go",
    "timestamp": datetime.now().isoformat(),
    "run_number": RUN_NUMBER,
    "total": len(task_ids),
    "pass": passes,
    "fail": fails,
    "pass_rate": round(passes / len(task_ids) * 100, 1),
    "lifeline_triggers": lifeline_count,
    "already_passed_skipped": skip_count,
    "total_time_s": round(total_elapsed, 1),
    "results": results,
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\n=== CONDITION B2 COMPLETE ===")
print(f"  Pass: {passes}/{len(task_ids)} ({summary['pass_rate']}%)")
print(f"  Lifeline triggered: {lifeline_count} tasks")
print(f"  Already passed in B: {skip_count} (skipped)")
print(f"  Time: {total_elapsed:.1f}s")
print(f"  Saved: {OUTPUT_FILE}")
