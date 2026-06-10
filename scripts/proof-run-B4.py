#!/usr/bin/env python3.10
"""Proof runner — Condition B4 (RICHER CONTEXT — function signatures + examples).
For each task, extract the function name and one example from test assertions.
Inject them BEFORE attempt 1. Max 2 M3 attempts. No DeepSeek reasoning.
Tests whether format visibility closes the 35pp gap to C (80%).
Labels: B4 (V2 richer context)
Usage: python3.10 proof-run-B4.py
Output: ~/.hermes/planning/self-improvement-loop/results/proof-B4.json
"""
import json, os, sys, time, subprocess, sqlite3, re
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
RESULTS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/results")
OUTPUT_FILE = os.path.join(RESULTS_DIR, "proof-B4.json")

RUN_NUMBER = 8

task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
print(f"=== PROOF RUN {RUN_NUMBER} — CONDITION B4: RICHER CONTEXT ===")
print(f"  Tasks: {len(task_ids)}")
print(f"  Logic: extract function signature + example → inject before attempt 1")
print(f"  Max 2 M3 attempts, no DeepSeek reasoning")
print(f"  Hypothesis: format visibility closes the 35pp gap")
print()

passes = 0
fails = 0
flips_vs_b = 0
flips_vs_b2 = 0
results = []
start_time = time.time()

db = sqlite3.connect(DB_PATH)


def extract_format_hints(task):
    """Extract function name and input/output examples from test assertions."""
    test_list = task.get('test_list', [])
    if not test_list:
        return None, None, None
    
    # Extract function name from first assert
    func_name = None
    for test in test_list:
        m = re.match(r'assert\s+(\w+)\(', test.strip())
        if m:
            func_name = m.group(1)
            break
    
    if not func_name:
        return None, None, None
    
    # Extract ONE example from first assertion: assert func(X) == Y
    examples = []
    for test in test_list:
        # Match: assert func(args) == expected
        m = re.match(r'assert\s+\w+\((.+?)\)\s*==\s*(.+)$', test.strip())
        if m:
            args_str = m.group(1).strip()
            expected = m.group(2).strip()
            examples.append((args_str, expected))
            if len(examples) >= 1:
                break
    
    example = examples[0] if examples else None
    return func_name, example, test_list


def build_format_hint(func_name, example, test_list):
    """Build a format hint string from extracted info."""
    lines = []
    lines.append(f"CRITICAL: Write a function named `{func_name}`.")
    
    if example:
        args, expected = example
        lines.append(f"Example: `{func_name}({args})` should return `{expected}`.")
    
    if len(test_list) > 1:
        lines.append(f"Your function must pass {len(test_list)} test assertions.")
    
    return "\n".join(lines)


def read_experience_memory(task_id):
    """Read past successes for this task (pass-first filter)."""
    entries = db.execute(
        "SELECT approach_tried, verdict, why FROM experience WHERE task_id=? AND run_number IN (1,2,3,4,5,6,7) ORDER BY CASE WHEN verdict='pass' THEN 0 ELSE 1 END, timestamp DESC",
        (task_id,)
    ).fetchall()
    if not entries:
        return ""
    
    passes_found = [e for e in entries if e[1] == 'pass']
    if passes_found:
        snippets = []
        for e in passes_found[:2]:
            code = e[0] or ""
            if code:
                snippets.append(f"Past success:\n```python\n{code[:400]}\n```")
        return "\n".join(snippets) if snippets else ""
    
    # No passes: cold solve (show nothing from memory)
    return ""


def extract_code(output):
    lines = output.split("\n")
    in_block = False
    code_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            code_lines.append(line)
    return "\n".join(code_lines) if code_lines else output


def run_oracle(task, code):
    test_setup = task.get("test_setup_code", "")
    test_list = task["test_list"]
    full_code = (test_setup or "") + "\n" + code + "\n" + "\n".join(test_list)
    try:
        exec(full_code, {})
        return True, ""
    except AssertionError as e:
        return False, f"AssertionError: {str(e)[:200]}"
    except SyntaxError as e:
        return False, f"SyntaxError: {str(e)[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def call_m3(prompt, timeout=180):
    try:
        result = subprocess.run(
            ["hermes", "-z", prompt, "-m", "MiniMax-M3", "--provider", "minimax"],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "HOME": os.path.expanduser("~")}
        )
        return result.stdout, time.time()
    except subprocess.TimeoutExpired:
        return "", time.time()
    except Exception as e:
        return f"ERROR: {e}", time.time()


# ---- Main loop ----
for i, task_id in enumerate(task_ids, 1):
    task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
    task = json.load(open(task_file))
    task_prompt = task['prompt']

    # Extract format hints
    func_name, example, test_list = extract_format_hints(task)
    format_hint = build_format_hint(func_name, example, test_list)

    # Check prior passes
    b_row = db.execute(
        "SELECT verdict FROM experience WHERE task_id=? AND run_number=2", (task_id,)
    ).fetchone()
    b2_row = db.execute(
        "SELECT verdict FROM experience WHERE task_id=? AND run_number=4", (task_id,)
    ).fetchone()
    b_passed = b_row and b_row[0] == 'pass'
    b2_passed = b2_row and b2_row[0] == 'pass'

    # Read experience memory
    exp_memory = read_experience_memory(task_id)

    # ---- Build attempt 1 prompt with format hints ----
    prefix = ""
    if format_hint:
        prefix = f"""FORMAT REQUIREMENTS:
{format_hint}

"""
    if exp_memory:
        prefix += f"""PAST EXPERIENCE:
{exp_memory[:800]}

"""
    
    prompt_a1 = f"""{prefix}Write a Python function that solves this problem. Follow the format requirements exactly. Return ONLY the function code in a single markdown code block. Do NOT include the assert tests.

Problem: {task_prompt}

```python
# Your solution here
```"""

    # ---- Attempt 1 ----
    a1_start = time.time()
    a1_output, _ = call_m3(prompt_a1)
    a1_time = time.time() - a1_start
    a1_code = extract_code(a1_output)
    a1_pass, a1_error = run_oracle(task, a1_code)

    # Extract actual function name from model output for NameError detection
    a1_func_match = re.search(r'^def\s+(\w+)', a1_code, re.MULTILINE) if a1_code else None
    a1_func = a1_func_match.group(1) if a1_func_match else None

    if a1_pass:
        passes += 1
        if not b_passed: flips_vs_b += 1
        if not b2_passed: flips_vs_b2 += 1
        print(f"  [{i}/{len(task_ids)}] {task_id} ✅ attempt_1 ({a1_time:.1f}s) [fn={func_name}]")
        
        db.execute(
            "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id[:16], task_id, "retry", a1_output[:500], "pass", "pass", "", time.time(), 1.0, RUN_NUMBER)
        )
        db.commit()
        
        results.append({
            "task_id": task_id, "condition": "B4", "run_number": RUN_NUMBER,
            "verdict": "PASS", "error": "",
            "attempts": 1,
            "func_name": func_name, "example": str(example),
            "solve_time_s": round(a1_time, 1),
            "path": "attempt_1_pass+format_hint",
        })
        continue

    # ---- Attempt 2: inject failure + reinforce format ----
    name_mismatch = ""
    if a1_func and a1_func != func_name:
        name_mismatch = f"\n\nCRITICAL: Your function was named `{a1_func}` but it MUST be named `{func_name}`. The test assertions call `{func_name}(...)`, not `{a1_func}(...)`."

    prompt_a2 = f"""FORMAT REQUIREMENTS:
{format_hint}

Your previous attempt FAILED with this error:
  {a1_error[:200]}{name_mismatch}

Write ONLY the corrected function. Follow the format requirements EXACTLY.

Problem: {task_prompt}

```python
# Corrected solution here
```"""

    a2_start = time.time()
    a2_output, _ = call_m3(prompt_a2)
    a2_time = time.time() - a2_start
    a2_code = extract_code(a2_output)
    a2_pass, a2_error = run_oracle(task, a2_code)

    total_time = a1_time + a2_time

    if a2_pass:
        passes += 1
        if not b_passed: flips_vs_b += 1
        if not b2_passed: flips_vs_b2 += 1
        print(f"  [{i}/{len(task_ids)}] {task_id} ✅ attempt_2 ({total_time:.1f}s) [a1: {a1_error[:40]}]")
        
        db.execute(
            "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id[:16], task_id, "retry", a2_output[:500], "pass", "pass", "", time.time(), 1.0, RUN_NUMBER)
        )
        db.commit()
        
        results.append({
            "task_id": task_id, "condition": "B4", "run_number": RUN_NUMBER,
            "verdict": "PASS", "error": "",
            "attempts": 2,
            "func_name": func_name, "example": str(example),
            "solve_time_s": round(total_time, 1),
            "path": f"attempt_1_fail({a1_error[:30]})+attempt_2_pass+format_hint",
        })
    else:
        fails += 1
        print(f"  [{i}/{len(task_ids)}] {task_id} ❌ ({total_time:.1f}s) [{a1_error[:50]} → {a2_error[:50]}]")
        
        db.execute(
            "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id[:16], task_id, "retry", a2_output[:500], "fail", "fail", a2_error, time.time(), 0.5, RUN_NUMBER)
        )
        db.commit()
        
        results.append({
            "task_id": task_id, "condition": "B4", "run_number": RUN_NUMBER,
            "verdict": "FAIL", "error": a2_error,
            "attempts": 2,
            "func_name": func_name, "example": str(example),
            "solve_time_s": round(total_time, 1),
            "path": f"attempt_1_fail({a1_error[:30]})+attempt_2_fail({a2_error[:30]})+format_hint",
        })

db.close()

# ---- Summary ----
total_elapsed = time.time() - start_time
pass_rate = round(passes / len(task_ids) * 100, 1)

summary = {
    "condition": "B4 (Richer Context — function signatures + examples before attempt 1)",
    "model": "MiniMax-M3 (max 2 attempts, no DeepSeek reasoning)",
    "provider": "minimax",
    "timestamp": datetime.now().isoformat(),
    "run_number": RUN_NUMBER,
    "total": len(task_ids),
    "pass": passes,
    "fail": fails,
    "pass_rate": pass_rate,
    "flips_vs_b": flips_vs_b,
    "flips_vs_b2": flips_vs_b2,
    "total_time_s": round(total_elapsed, 1),
    "results": results,
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\n=== CONDITION B4 COMPLETE ===")
print(f"  Pass: {passes}/{len(task_ids)} ({pass_rate}%)")
print(f"  Flips vs B (15%): {flips_vs_b}")
print(f"  Flips vs B2 (45%): {flips_vs_b2}")
print(f"  Time: {total_elapsed:.1f}s")
print(f"  Saved: {OUTPUT_FILE}")

# Quick comparison
print(f"\n  B (memory):       15% (3/20)")
print(f"  B3b (context7):   35% (7/20)")
print(f"  B2 (reasoning):   45% (9/20)")
print(f"  B4 (rich ctx):    {pass_rate}% ({passes}/{len(task_ids)})")
print(f"  C (cheat):        80% (16/20)")
