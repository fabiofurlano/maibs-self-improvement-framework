#!/usr/bin/env python3.10
"""Proof runner — Condition B7a (Format Hint + Step-by-Step Prompt).

For each of the 20 MBPP test tasks, run TWO sub-conditions in the same pass:
  A. B4-control:    format hint only (the B4-local baseline = 60%)
  B. B7a-stepwise:  format hint + explicit reasoning scaffold
                     (decompose problem → solve sub-steps → write code)

Hypothesis: small local Gemma 4 E4B gets the format right (B4 = 60%) but
fails on the 5 stuck tasks because it jumps straight to code without
planning. An explicit "think before you code" scaffold should unstick them.

Anti-cheat: no memory recall in this run — B7a isolates the scaffold effect
from the recall effect (which B6 already tested and FALSIFIED, 8/20 vs 10/20).

Output: ~/.hermes/planning/self-improvement-loop/results/proof-B7a.json
Log:    ~/.hermes/planning/self-improvement-loop/results/proof-B7a-step-log.txt
"""
import json, os, sys, time, re, sqlite3, requests
from datetime import datetime
from pathlib import Path

# === CONFIG ===
TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/planning/self-improvement-loop/proof-tasks.txt")
if not os.path.exists(PROOF_TASKS):
    PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
RESULTS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/results")
OUTPUT_FILE = os.path.join(RESULTS_DIR, "proof-B7a.json")
STEP_LOG = os.path.join(RESULTS_DIR, "proof-B7a-step-log.txt")

LLAMA_URL = "http://localhost:8080/v1/chat/completions"
LLAMA_MODEL = "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
RUN_NUMBER = 11  # Run 11 = B7a

# === HELPERS (mirror B6) ===
def extract_format_hints(task):
    test_list = task.get('test_list', [])
    if not test_list: return None, None, None
    func_name = None
    for test in test_list:
        m = re.match(r'assert\s+(\w+)\(', test.strip())
        if m:
            func_name = m.group(1); break
    if not func_name: return None, None, None
    examples = []
    for test in test_list:
        m = re.match(r'assert\s+\w+\((.+?)\)\s*==\s*(.+)$', test.strip())
        if m:
            args_str = m.group(1).strip()
            expected = m.group(2).strip()
            examples.append((args_str, expected))
            if len(examples) >= 1: break
    example = examples[0] if examples else None
    return func_name, example, test_list

def build_format_hint(func_name, example, test_list):
    lines = []
    lines.append(f"CRITICAL: Write a function named `{func_name}`.")
    if example:
        args, expected = example
        lines.append(f"Example: `{func_name}({args})` should return `{expected}`.")
    if len(test_list) > 1:
        lines.append(f"Your function must pass {len(test_list)} test assertions.")
    return "\n".join(lines)

# === B7a SCAFFOLD ===
STEP_BY_STEP_PROMPT = """Before writing any code, work through this problem step by step.
Do NOT skip steps. Do NOT write the function until you've finished the analysis.

STEP 1 — UNDERSTAND the problem:
  Restate in one sentence what input the function takes and what it returns.
  Identify any edge cases (empty input, negative numbers, single-element lists, etc.).

STEP 2 — EXAMPLES:
  Walk through the example provided in the FORMAT REQUIREMENTS.
  Show exactly what the function receives, what it should return, and WHY.

STEP 3 — APPROACH:
  Pick a strategy (e.g. iterate, recurse, sort, build a set, use a loop counter).
  In 1-2 sentences, say how the strategy will produce the correct output for the example.

STEP 4 — PSEUDOCODE:
  Write 3-6 lines of plain-English pseudocode for the function body. No Python yet.

STEP 5 — IMPLEMENT:
  Now write the actual Python function. Follow the pseudocode. Use the exact
  function name from the FORMAT REQUIREMENTS.

Write your full response (steps 1-5) below, then put the final Python function
in a single ```python``` code block at the end.
"""

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

def extract_code(output):
    lines = output.split("\n")
    in_block, code_lines = False, []
    for line in lines:
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            code_lines.append(line)
    return "\n".join(code_lines) if code_lines else output

def call_gemma(prompt, timeout=240):
    """B7a gives Gemma more tokens (1000 vs 500) because the scaffold eats
    context before the final code block."""
    try:
        r = requests.post(LLAMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000, "temperature": 0
        }, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], time.time()
    except requests.Timeout:
        return "", time.time()
    except Exception as e:
        return f"ERROR: {e}", time.time()

# === MAIN LOOP ===
def main():
    task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
    print(f"=== PROOF RUN {RUN_NUMBER} — CONDITION B7a: FORMAT HINT + STEP-BY-STEP SCAFFOLD ===")
    print(f"  Tasks: {len(task_ids)} (same 20 as B4-local / B6)")
    print(f"  Model: {LLAMA_MODEL}")
    print(f"  Sub-conditions: B4-control (format only) vs B7a-stepwise (format + scaffold)")
    print(f"  Scaffold: 5-step explicit reasoning (understand→example→approach→pseudocode→implement)")
    print()

    step_log_lines = []
    step_log_lines.append(f"B7a Step Log — {datetime.now().isoformat()}")
    step_log_lines.append("="*80)

    db = sqlite3.connect(DB_PATH)
    passes_b4, passes_b7, fails_b4, fails_b7 = 0, 0, 0, 0
    results = []
    start = time.time()

    for i, task_id in enumerate(task_ids, 1):
        task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
        task = json.load(open(task_file))
        task_prompt = task['prompt']
        func_name, example, test_list = extract_format_hints(task)
        format_hint = build_format_hint(func_name, example, test_list) if func_name else ""

        step_log_lines.append(f"\n[{i:2d}] {task_id}: {task_prompt[:80]}")

        # ---- B4-CONTROL attempt (identical to B6's control) ----
        prompt_b4 = f"""FORMAT REQUIREMENTS:
{format_hint}

Write a Python function that solves this problem. Follow the format requirements exactly. Return ONLY the function code in a single markdown code block. Do NOT include the assert tests.

Problem: {task_prompt}

```python
# Your solution here
```"""
        a1_b4, _ = call_gemma(prompt_b4, timeout=180)
        code_b4 = extract_code(a1_b4)
        passed_b4, err_b4 = run_oracle(task, code_b4)
        if passed_b4: passes_b4 += 1
        else: fails_b4 += 1

        # ---- B7a-STEPWISE attempt ----
        prompt_b7a = f"""{STEP_BY_STEP_PROMPT}

FORMAT REQUIREMENTS:
{format_hint}

Problem: {task_prompt}
"""
        a1_b7, _ = call_gemma(prompt_b7a, timeout=240)
        code_b7 = extract_code(a1_b7)
        passed_b7, err_b7 = run_oracle(task, code_b7)
        if passed_b7: passes_b7 += 1
        else: fails_b7 += 1

        # Log scaffold steps presence
        step_log_lines.append(f"  B4 control: {'PASS' if passed_b4 else 'FAIL'} ({err_b4[:80]})")
        step_log_lines.append(f"  B7a stepwise: {'PASS' if passed_b7 else 'FAIL'} ({err_b7[:80]})")
        if a1_b7 and not a1_b7.startswith("ERROR"):
            a1_lower = a1_b7.lower()
            for step in ["step 1", "step 2", "step 3", "step 4", "step 5"]:
                step_log_lines.append(f"  {step.upper()} present: {step in a1_lower}")

        flip = "FLIP!" if (not passed_b4 and passed_b7) else ("REGRESS!" if (passed_b4 and not passed_b7) else "")
        print(f"  [{i:2d}/{len(task_ids)}] {task_id}: B4={'P' if passed_b4 else 'F'} B7a={'P' if passed_b7 else 'F'} {flip}")

        results.append({
            "task_id": task_id,
            "task_prompt": task_prompt[:80],
            "func_name": func_name,
            "b4_passed": passed_b4, "b4_error": err_b4,
            "b7a_passed": passed_b7, "b7a_error": err_b7,
            "b7a_had_all_steps": all(s in a1_b7.lower() for s in ["step 1","step 2","step 3","step 4","step 5"]) if not a1_b7.startswith("ERROR") else False,
            "flip": (not passed_b4 and passed_b7),
            "regress": (passed_b4 and not passed_b7),
        })

    elapsed = time.time() - start
    db.close()

    b4_pct = round(passes_b4 / len(task_ids) * 100, 1)
    b7a_pct = round(passes_b7 / len(task_ids) * 100, 1)
    n_flips = sum(1 for r in results if r["flip"])
    n_regress = sum(1 for r in results if r["regress"])

    # Highlight the 5 stuck tasks
    STUCK = {"MBPP/22", "MBPP/264", "MBPP/268", "MBPP/448", "MBPP/473"}
    stuck_results = [r for r in results if r["task_id"] in STUCK]
    stuck_flips = [r["task_id"] for r in stuck_results if r["flip"]]

    summary = {
        "condition": "B7a (Format Hint + Step-by-Step Scaffold)",
        "model": LLAMA_MODEL,
        "timestamp": datetime.now().isoformat(),
        "run_number": RUN_NUMBER,
        "total": len(task_ids),
        "b4_control": {"pass": passes_b4, "fail": fails_b4, "pass_rate": b4_pct},
        "b7a_stepwise": {"pass": passes_b7, "fail": fails_b7, "pass_rate": b7a_pct},
        "n_flips": n_flips, "n_regress": n_regress,
        "stuck_tasks_flip": stuck_flips,
        "total_time_s": round(elapsed, 1),
        "results": results,
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    with open(STEP_LOG, "w") as f:
        f.write("\n".join(step_log_lines))

    print(f"\n=== CONDITION B7a COMPLETE ===")
    print(f"  B4-control (format only):     {passes_b4}/{len(task_ids)} = {b4_pct}%")
    print(f"  B7a-stepwise (format + scaf): {passes_b7}/{len(task_ids)} = {b7a_pct}%")
    print(f"  Flips:   {n_flips}")
    print(f"  Regress: {n_regress}")
    print(f"  Stuck tasks flipped: {stuck_flips if stuck_flips else 'NONE'}")
    print(f"  Time:    {elapsed:.1f}s")
    print(f"  Saved:   {OUTPUT_FILE}")
    print(f"  Step log: {STEP_LOG}")
    print(f"\n  Verdict: {'B7a > B4 ✅' if b7a_pct > b4_pct else 'B7a <= B4 (no improvement)'}")
    if b7a_pct > b4_pct:
        flips = [r for r in results if r["flip"]]
        print(f"  Flipped tasks: {[r['task_id'] for r in flips]}")

if __name__ == "__main__":
    main()
