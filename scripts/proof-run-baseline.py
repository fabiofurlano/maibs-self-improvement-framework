#!/usr/bin/env python3.10
"""Proof runner — Condition A (BASELINE, NO memory).
Solves 20 MBPP tasks from scratch with no prior attempt context.
Usage: python3.10 proof-run-baseline.py
Output: ~/.hermes/planning/self-improvement-loop/results/proof-A.json
"""
import json, os, sys, time, subprocess
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
RESULTS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/results")
OUTPUT_FILE = os.path.join(RESULTS_DIR, "proof-A.json")

RUN_NUMBER = 0  # Run 0 = baseline, no memory

# Load proof task list
task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
print(f"=== PROOF RUN {RUN_NUMBER} — CONDITION A: NO MEMORY (BASELINE) ===")
print(f"  Tasks: {len(task_ids)}")
print(f"  Model: MiniMax-M3 via minimax")
print()

passes = 0
fails = 0
results = []
start_time = time.time()

for i, task_id in enumerate(task_ids, 1):
    task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
    task = json.load(open(task_file))

    # Build prompt with NO memory block (condition A)
    solve_prompt = f"""Write a Python function that solves this problem. Return ONLY the function code in a single markdown code block.

Problem: {task['prompt']}

```python
# Your solution here
```"""

    # Solve via hermes CLI
    t_start = time.time()
    try:
        result = subprocess.run(
            ["hermes", "-z", solve_prompt, "-m", "MiniMax-M3", "--provider", "minimax"],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "HOME": os.path.expanduser("~")}
        )
        solve_output = result.stdout
        elapsed = time.time() - t_start
    except subprocess.TimeoutExpired:
        solve_output = ""
        elapsed = 180
    except Exception as e:
        solve_output = f"ERROR: {e}"
        elapsed = time.time() - t_start

    # Extract code from markdown block
    agent_lines = []
    in_block = False
    for line in solve_output.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            agent_lines.append(line)

    agent_code = "\n".join(agent_lines) if agent_lines else solve_output

    # Run oracle
    test_setup = task.get("test_setup_code", "")
    test_list = task["test_list"]

    full_code = (test_setup or "") + "\n" + agent_code + "\n" + "\n".join(test_list)
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

    # Check for rate limit
    if "usage limit exceeded" in solve_output.lower():
        verdict = "FAIL"
        error_msg = "RATE_LIMIT"

    if verdict == "PASS":
        passes += 1
        status = "✅"
    else:
        fails += 1
        status = "❌"

    err_short = f" ({error_msg[:60]})" if error_msg else ""
    print(f"  [{i}/{len(task_ids)}] {task_id} {status} ({elapsed:.1f}s){err_short}")

    results.append({
        "task_id": task_id,
        "condition": "A",
        "run_number": RUN_NUMBER,
        "verdict": verdict,
        "error": error_msg,
        "solve_time_s": round(elapsed, 1),
        "solve_output_trimmed": solve_output[:300] if verdict == "FAIL" else "",
    })

    # Rate-limit check — warn and continue, don't abort mid-run
    if "usage limit exceeded" in solve_output.lower():
        print(f"  ⚠️  RATE LIMIT HIT at task {task_id}. Continuing but marking as fail.")

# Save results
os.makedirs(RESULTS_DIR, exist_ok=True)
total_elapsed = time.time() - start_time
summary = {
    "condition": "A (baseline, no memory)",
    "model": "MiniMax-M3",
    "provider": "minimax",
    "timestamp": datetime.now().isoformat(),
    "run_number": RUN_NUMBER,
    "total": len(task_ids),
    "pass": passes,
    "fail": fails,
    "pass_rate": round(passes / len(task_ids) * 100, 1),
    "total_time_s": round(total_elapsed, 1),
    "results": results,
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\n=== CONDITION A COMPLETE ===")
print(f"  Pass: {passes}/{len(task_ids)} ({summary['pass_rate']}%)")
print(f"  Time: {total_elapsed:.1f}s")
print(f"  Saved: {OUTPUT_FILE}")
