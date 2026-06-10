#!/usr/bin/env python3.10
"""Batch runner for self-improvement loop Stage 2, Run 1 (baseline, no memory).
Runs batches of 25 tasks in foreground, writes progress to wiki after each batch.
Usage: python3.10 batch-runner.py <batch_start> <batch_end> <run_id>

Example: python3.10 batch-runner.py 1 25 1
"""
import json, os, sys, time, subprocess, sqlite3, hashlib
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
ORDERING_FILE = os.path.join(TASKS_DIR, "retry_order_seed1.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
SOLVE_OUTPUT_FILE = "/tmp/sil-solve-output.txt"
ORACLE_RESULT_FILE = "/tmp/sil-oracle-result.txt"
WIKI_LOG_FILE = os.path.expanduser("~/.hermes/planning/self-improvement-loop/batch-log.md")

BATCH_START = int(sys.argv[1])
BATCH_END = int(sys.argv[2])
RUN_ID = int(sys.argv[3]) if len(sys.argv) > 3 else 1

# Read ordering
order = [line.strip() for line in open(ORDERING_FILE) if line.strip().startswith("MBPP/")]
total = len(order)

batch_tasks = order[BATCH_START-1:BATCH_END]
print(f"=== BATCH {BATCH_START}-{BATCH_END} (RUN {RUN_ID}) ===")
print(f"  Tasks in batch: {len(batch_tasks)}")
print(f"  Total retry set: {total}")
print()

passes = 0
fails = 0

for i, task_id in enumerate(batch_tasks, start=BATCH_START):
    task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
    if not os.path.exists(task_file):
        print(f"  [{i}/{BATCH_END}] {task_id} ... SKIP (no file)")
        continue
    
    task = json.load(open(task_file))
    prompt_text = task["prompt"]
    
    # Build solve prompt
    solve_prompt = f"""Write a Python function that solves this problem. Return ONLY the function code in a markdown code block.

Problem: {prompt_text}

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
    try:
        import importlib.util
        # Inline oracle logic
        test_setup = task.get("test_setup_code", "")
        test_list = task["test_list"]
        
        # Extract code from solve output
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
        
        # Run tests
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
        
    except Exception as e:
        verdict = "FAIL"
        error_msg = f"Oracle error: {str(e)[:200]}"
    
    # Write oracle result
    with open(ORACLE_RESULT_FILE, "w") as f:
        f.write(f"ORACLE_{verdict}")
        if error_msg:
            f.write(f"\nError: {error_msg}")
    
    # Record in DB
    task_hash = hashlib.sha256(task_id.encode()).hexdigest()[:16]
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_hash, task_id, "retry", solve_output[:500], verdict.lower(), verdict.lower(), error_msg, time.time(), 1.0, RUN_ID)
    )
    db.commit()
    db.close()
    
    status = "✅" if verdict == "PASS" else "❌"
    if verdict == "PASS":
        passes += 1
    else:
        fails += 1
    
    err_short = f" ({error_msg[:60]})" if error_msg else ""
    print(f"  [{i}/{BATCH_END}] {task_id} {status} ({elapsed:.1f}s){err_short}")

# Batch summary
print(f"\n--- BATCH {BATCH_START}-{BATCH_END} SUMMARY ---")
print(f"  Pass: {passes}/{len(batch_tasks)}")
print(f"  Fail: {fails}/{len(batch_tasks)}")

# Count total passes so far
db = sqlite3.connect(DB_PATH)
total_passes = db.execute("SELECT COUNT(*) FROM experience WHERE verdict='pass' AND run_number=?", (RUN_ID,)).fetchone()[0]
total_done = db.execute("SELECT COUNT(*) FROM experience WHERE run_number=?", (RUN_ID,)).fetchone()[0]
db.close()

print(f"  Cumulative: {total_passes}/{total_done} passes")
print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")

# Write one line to wiki log
log_entry = f"| Batch {BATCH_START}-{BATCH_END} | {total_done}/{total} | {total_passes} | {datetime.now().strftime('%H:%M')} |\n"
os.makedirs(os.path.dirname(WIKI_LOG_FILE), exist_ok=True)

if not os.path.exists(WIKI_LOG_FILE):
    with open(WIKI_LOG_FILE, "w") as f:
        f.write("# Run 1 Batch Log (Baseline, No Memory)\n\n")
        f.write("| Batch | Tasks Done | Passes | Time |\n")
        f.write("|-------|-----------|--------|------|\n")

with open(WIKI_LOG_FILE, "a") as f:
    f.write(log_entry)

print(f"\n  Wiki log: {WIKI_LOG_FILE}")
