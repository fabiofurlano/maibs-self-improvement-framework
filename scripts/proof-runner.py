#!/usr/bin/env python3.10
"""Proof runner — Run 2 with failure memory.
Solves the same 20 tasks from Run 1, injecting each task's own failure as memory.
Usage: python3.10 proof-runner.py
"""
import json, os, sys, time, subprocess, sqlite3, hashlib
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
SOLVE_OUTPUT_FILE = "/tmp/sil-solve-output.txt"
ORACLE_RESULT_FILE = "/tmp/sil-oracle-result.txt"

RUN_NUMBER = 2  # Run 2 = with memory

# Load proof task list
task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
print(f"=== PROOF RUN 2 (WITH MEMORY) ===")
print(f"  Tasks: {len(task_ids)}")
print(f"  Pattern: inject each task's own Run 1 failure as memory")
print()

flips = 0
total = len(task_ids)

for i, task_id in enumerate(task_ids, 1):
    task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
    task = json.load(open(task_file))
    
    # Get Run 1 failure for this task
    db = sqlite3.connect(DB_PATH)
    prev = db.execute(
        "SELECT approach_tried, why, verdict FROM experience WHERE task_id=? AND run_number=1",
        (task_id,)
    ).fetchone()
    db.close()
    
    if not prev:
        print(f"  [{i}/{total}] {task_id} ... SKIP (no Run 1 data)")
        continue
    
    prev_code = prev[0][:300] if prev[0] else ""
    prev_error = prev[1] or "unknown"
    prev_verdict = prev[2]
    
    # Build prompt WITH failure memory
    if prev_verdict == "fail":
        memory_block = f"""## YOUR PREVIOUS ATTEMPT (FAILED)

You previously tried this approach:
```python
{prev_code}
```

It failed with: {prev_error}

**Learn from this mistake.** The function name or approach was wrong. Look at the error carefully and write a CORRECTED solution.

---
"""
    else:
        memory_block = ""
    
    solve_prompt = f"""{memory_block}Write a Python function that solves this problem. Return ONLY the function code in a markdown code block.

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
    
    # Save solve output
    with open(SOLVE_OUTPUT_FILE, "w") as f:
        f.write(solve_output)
    
    # Run oracle
    test_setup = task.get("test_setup_code", "")
    test_list = task["test_list"]
    
    lines = solve_output.split("\n")
    agent_lines = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            agent_lines.append(line)
    
    agent_code = "\n".join(agent_lines) if agent_lines else solve_output
    
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
    if "usage limit exceeded" in solve_output:
        verdict = "FAIL"
        error_msg = "RATE_LIMIT"
    
    # Record in DB
    task_hash = hashlib.sha256(task_id.encode()).hexdigest()[:16]
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_hash, task_id, "retry", solve_output[:500], verdict.lower(), verdict.lower(), error_msg, time.time(), 1.0, RUN_NUMBER)
    )
    db.commit()
    db.close()
    
    # Did it flip?
    flipped = (prev_verdict == "fail" and verdict == "PASS")
    if flipped:
        flips += 1
    
    status = "✅" if verdict == "PASS" else "❌"
    flip_marker = " 🔄 FLIP!" if flipped else ""
    err_short = f" ({error_msg[:60]})" if error_msg else ""
    print(f"  [{i}/{total}] {task_id} {status}{flip_marker} ({elapsed:.1f}s){err_short}")

# Summary
print(f"\n=== PROOF RESULT ===")
print(f"  Tasks: {total}")
print(f"  Flips (FAIL→PASS): {flips}")
print(f"  Flip rate: {flips/total*100:.1f}%")
print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")

if flips > 0:
    print(f"\n  ✅ CONCEPT PROVEN: {flips} tasks improved with failure memory")
else:
    print(f"\n  ❌ No improvement from failure memory")
