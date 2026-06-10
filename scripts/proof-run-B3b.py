#!/usr/bin/env python3.10
"""Proof runner — Condition B3b (CONTEXT7-FIRST).
Context7 library docs injected BEFORE attempt 1 for library tasks.
Non-library tasks: experience memory only (same as B).
Max 2 M3 attempts. No DeepSeek reasoning, no web search fallback.
Compares against B2's 45%.
Usage: python3.10 proof-run-B3b.py
Output: ~/.hermes/planning/self-improvement-loop/results/proof-B3b.json
"""
import json, os, sys, time, subprocess, sqlite3, re
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
RESULTS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/results")
OUTPUT_FILE = os.path.join(RESULTS_DIR, "proof-B3b.json")

RUN_NUMBER = 7

task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
print(f"=== PROOF RUN {RUN_NUMBER} — CONDITION B3b: CONTEXT7-FIRST ===")
print(f"  Tasks: {len(task_ids)}")
print(f"  Logic: library tasks → Context7 docs BEFORE attempt 1 → max 2 M3 attempts")
print(f"  Non-library tasks: experience memory only → max 2 M3 attempts")
print(f"  No DeepSeek reasoning, no web search fallback")
print()

passes = 0
fails = 0
context7_calls = 0
context7_tasks = 0
flips_vs_b = 0  # tasks that failed in B but passed in B3b
results = []
start_time = time.time()

db = sqlite3.connect(DB_PATH)

# ---- Library detection from task prompt ----
LIBRARY_HINTS = {
    'numpy': ['array', 'matrix', 'vector', 'ndarray', 'linspace', 'arange', 'numpy'],
    'pandas': ['dataframe', 'series', 'csv', 'read_csv', 'groupby'],
    'math': ['sqrt', 'log', 'sin', 'cos', 'ceil', 'floor', 'pow', 'math.'],
    'itertools': ['permutations', 'combinations', 'product', 'chain', 'itertools'],
    'collections': ['counter', 'deque', 'defaultdict', 'ordereddict', 'namedtuple', 'collections'],
    're': ['regex', 'pattern', 'match', 'search', 'sub', 're.'],
    'functools': ['reduce', 'lru_cache', 'partial', 'functools'],
    'heapq': ['heap', 'heappush', 'heappop', 'nsmallest', 'nlargest', 'heapq'],
    'statistics': ['mean', 'median', 'mode', 'stdev', 'variance', 'statistics'],
    'random': ['random', 'randint', 'shuffle', 'choice', 'sample'],
    'bisect': ['bisect', 'bisect_left', 'bisect_right', 'insort'],
}
LIBRARY_KEYWORDS = {}  # inverted: kw → lib
for lib, kws in LIBRARY_HINTS.items():
    for kw in kws:
        LIBRARY_KEYWORDS[kw] = lib


def detect_library(task_prompt):
    """Return (lib_name, matched_keyword) or (None, None)."""
    prompt_lower = task_prompt.lower()
    for kw, lib in sorted(LIBRARY_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if kw in prompt_lower:
            return lib, kw
    return None, None


def search_context7(lib_name, task_prompt):
    """Search web for library docs/usage relevant to this task."""
    try:
        from ddgs import DDGS
        query = f"{lib_name} Python how to {task_prompt[:80]}"
        ddgs = DDGS()
        results_list = list(ddgs.text(query, max_results=3))
        if not results_list:
            return ""
        parts = []
        for r in results_list[:2]:
            title = r.get('title', '')
            body = r.get('body', '')[:500]
            url = r.get('href', '')
            if body:
                parts.append(f"**{title}**\n{body}\nSource: {url}")
        return "\n\n".join(parts) if parts else ""
    except Exception as e:
        print(f"      [Context7 search error: {e}]", end="", flush=True)
    return ""


def read_experience_memory(task_id):
    """Read past experience for this task from the DB (pass-first filter)."""
    entries = db.execute(
        "SELECT approach_tried, verdict, why FROM experience WHERE task_id=? AND run_number IN (1,2,3) ORDER BY CASE WHEN verdict='pass' THEN 0 ELSE 1 END, timestamp DESC",
        (task_id,)
    ).fetchall()
    if not entries:
        return ""
    
    # Pass-first filter
    passes_found = [e for e in entries if e[1] == 'pass']
    if passes_found:
        snippets = []
        for e in passes_found[:2]:
            code = e[0] or ""
            if code:
                snippets.append(f"Past success:\n```python\n{code[:400]}\n```")
        return "\n".join(snippets) if snippets else ""
    
    # No passes: cold solve (show nothing)
    return ""


def extract_code(output):
    """Extract markdown code block from hermes -z output."""
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
    """Test code against task assert statements. Returns (passed, error_msg)."""
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
    """Call MiniMax M3 via hermes CLI."""
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

    # Extract function name from tests
    func_name = "unknown"
    for test in task.get('test_list', []):
        m = re.match(r'assert\s+(\w+)\(', test.strip())
        if m:
            func_name = m.group(1)
            break

    # Check if task passed in B (run 2)
    b_row = db.execute(
        "SELECT verdict FROM experience WHERE task_id=? AND run_number=2", (task_id,)
    ).fetchone()
    b_passed = b_row and b_row[0] == 'pass'

    # ---- Context7-first for library tasks ----
    lib_match, kw = detect_library(task_prompt)
    context7_docs = ""
    if lib_match:
        context7_tasks += 1
        context7_calls += 1
        context7_docs = search_context7(lib_match, task_prompt)

    # ---- Build attempt 1 prompt ----
    exp_memory = read_experience_memory(task_id)

    prefix = ""
    if context7_docs:
        prefix = f"""LIBRARY REFERENCE ({lib_match} — detected from task description):
{context7_docs[:1200]}

Use the library reference above to help write your solution.

"""
    if exp_memory:
        prefix += f"""PAST EXPERIENCE:
{exp_memory[:800]}

"""

    prompt_a1 = f"""{prefix}Write a Python function that solves this problem. Return ONLY the function code in a single markdown code block. Do NOT include the assert tests.

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

    if a1_pass:
        passes += 1
        if not b_passed:
            flips_vs_b += 1
        lib_label = f" [{lib_match}]" if lib_match else ""
        print(f"  [{i}/{len(task_ids)}] {task_id} ✅ attempt_1{lib_label} ({a1_time:.1f}s)")
        
        db.execute(
            "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id[:16], task_id, "retry", a1_output[:500], "pass", "pass", "", time.time(), 1.0, RUN_NUMBER)
        )
        db.commit()
        
        results.append({
            "task_id": task_id, "condition": "B3b", "run_number": RUN_NUMBER,
            "verdict": "PASS", "error": "",
            "attempts": 1, "lib_detected": lib_match,
            "solve_time_s": round(a1_time, 1),
            "path": "attempt_1_pass" + (f"+context7:{lib_match}" if lib_match else ""),
        })
        continue

    # ---- Attempt 2: inject failure context ----
    prefix_a2 = ""
    if context7_docs:
        prefix_a2 = f"LIBRARY REFERENCE ({lib_match}):\n{context7_docs[:800]}\n\n"
    
    prompt_a2 = f"""{prefix_a2}Your previous attempt failed with this error: {a1_error[:200]}

The function name must be `{func_name}`. Fix the code.

Previous code:
```python
{a1_code[:500]}
```

Write ONLY the corrected function in a single markdown code block:

Problem: {task_prompt}

```python
# Corrected solution here
```"""

    a2_start = time.time()
    a2_output, _ = call_m3(prompt_a2)
    a2_time = time.time() - a2_start
    a2_code = extract_code(a2_output)
    a2_pass, a2_error = run_oracle(task, a2_code)

    if a2_pass:
        passes += 1
        if not b_passed:
            flips_vs_b += 1
        lib_label = f" [{lib_match}]" if lib_match else ""
        print(f"  [{i}/{len(task_ids)}] {task_id} ✅ attempt_2{lib_label} ({a1_time+a2_time:.1f}s) [a1: {a1_error[:40]}]")
        
        db.execute(
            "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id[:16], task_id, "retry", a2_output[:500], "pass", "pass", "", time.time(), 1.0, RUN_NUMBER)
        )
        db.commit()
        
        results.append({
            "task_id": task_id, "condition": "B3b", "run_number": RUN_NUMBER,
            "verdict": "PASS", "error": "",
            "attempts": 2, "lib_detected": lib_match,
            "solve_time_s": round(a1_time + a2_time, 1),
            "path": "attempt_1_fail+attempt_2_pass" + (f"+context7:{lib_match}" if lib_match else ""),
        })
    else:
        fails += 1
        b2_failed = b_row and b_row[0] == 'fail' if b_row else True
        lib_label = f" [{lib_match}]" if lib_match else ""
        print(f"  [{i}/{len(task_ids)}] {task_id} ❌ ({a1_time+a2_time:.1f}s) [{a1_error[:60]} → {a2_error[:60]}]{lib_label}")
        
        db.execute(
            "INSERT INTO experience (problem_signature, task_id, split, approach_tried, outcome, verdict, why, timestamp, confidence, run_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id[:16], task_id, "retry", a2_output[:500], "fail", "fail", a2_error, time.time(), 0.5, RUN_NUMBER)
        )
        db.commit()
        
        results.append({
            "task_id": task_id, "condition": "B3b", "run_number": RUN_NUMBER,
            "verdict": "FAIL", "error": a2_error,
            "attempts": 2, "lib_detected": lib_match,
            "solve_time_s": round(a1_time + a2_time, 1),
            "path": f"attempt_1_fail({a1_error[:40]})+attempt_2_fail({a2_error[:40]})" + (f"+context7:{lib_match}" if lib_match else ""),
        })

db.close()

# ---- Summary ----
total_elapsed = time.time() - start_time
pass_rate = round(passes / len(task_ids) * 100, 1)

summary = {
    "condition": "B3b (Context7-first — library docs before attempt 1)",
    "model": "MiniMax-M3 (max 2 attempts, no DeepSeek reasoning)",
    "provider": "minimax",
    "timestamp": datetime.now().isoformat(),
    "run_number": RUN_NUMBER,
    "total": len(task_ids),
    "pass": passes,
    "fail": fails,
    "pass_rate": pass_rate,
    "context7_calls": context7_calls,
    "context7_tasks": context7_tasks,
    "flips_vs_b": flips_vs_b,
    "total_time_s": round(total_elapsed, 1),
    "results": results,
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\n=== CONDITION B3b COMPLETE ===")
print(f"  Pass: {passes}/{len(task_ids)} ({pass_rate}%)")
print(f"  Context7 calls: {context7_calls} ({context7_tasks} library tasks)")
print(f"  Flips vs B (15%): {flips_vs_b}")
print(f"  Time: {total_elapsed:.1f}s")
print(f"  Saved: {OUTPUT_FILE}")
