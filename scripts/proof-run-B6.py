#!/usr/bin/env python3.10
"""Proof runner — Condition B6 (Richer Context + EXPERIENCE_INDEX recall).

For each of the 20 MBPP test tasks, run TWO sub-conditions in the same pass:
  A. B4-control: format hint only (the B4-local baseline = 60%)
  B. B6-recall:  format hint + recall of a real past solution from EXPERIENCE_INDEX

The pool of recalled solutions is the 17+ passing tasks seeded by seed_memory.py
in experiences/coding/ (non-test MBPP tasks, written with task_id-prefixed names).

Hypothesis: if the 5 Gemma-specific stuck tasks (MBPP/22, 264, 268, 448, 473) can
find a STRUCTURALLY similar past solution, recalling it as a worked example
should flip some of them.

Anti-cheat: pool only contains tasks outside the 20 test set (enforced by seed_memory.py).
Anti-pollution: this script does NOT seed new memory; it only reads from the index.

Output: ~/.hermes/planning/self-improvement-loop/results/proof-B6.json
Log:    ~/.hermes/planning/self-improvement-loop/results/proof-B6-match-log.txt
"""
import json, os, sys, time, re, sqlite3, requests
from datetime import datetime
from pathlib import Path

# === CONFIG ===
TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/planning/self-improvement-loop/proof-tasks.txt")
# Fall back if typo above doesn't exist:
if not os.path.exists(PROOF_TASKS):
    PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
RESULTS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/results")
OUTPUT_FILE = os.path.join(RESULTS_DIR, "proof-B6.json")
MATCH_LOG = os.path.join(RESULTS_DIR, "proof-B6-match-log.txt")

REPO_ROOT = "/tmp/maibs-self-improvement-framework"
INDEX_PATH = f"{REPO_ROOT}/experiences/EXPERIENCE_INDEX.md"
CODING_DIR = f"{REPO_ROOT}/experiences/coding"

LLAMA_URL = "http://localhost:8080/v1/chat/completions"
LLAMA_MODEL = "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
RUN_NUMBER = 10  # Run 10 = B6

JACCARD_THRESHOLD = 3  # min token overlap for "similar enough to recall"

# === HELPERS ===
def tokenize(text):
    STOP = {"a","an","the","of","to","in","on","for","and","or","is","it","this","that","with","as","by","at","be","from"}
    return [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP]

def jaccard_size(a_tokens, b_tokens):
    """Return size of intersection (used as similarity measure, not ratio)."""
    return len(set(a_tokens) & set(b_tokens))

def extract_format_hints(task):
    """Same as B4-local."""
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
    """Same as B4-local."""
    lines = []
    lines.append(f"CRITICAL: Write a function named `{func_name}`.")
    if example:
        args, expected = example
        lines.append(f"Example: `{func_name}({args})` should return `{expected}`.")
    if len(test_list) > 1:
        lines.append(f"Your function must pass {len(test_list)} test assertions.")
    return "\n".join(lines)

def run_oracle(task, code):
    """Run test assertions against generated code."""
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

def call_gemma(prompt, timeout=180):
    try:
        r = requests.post(LLAMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500, "temperature": 0
        }, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], time.time()
    except requests.Timeout:
        return "", time.time()
    except Exception as e:
        return f"ERROR: {e}", time.time()

# === EXPERIENCE INDEX READER ===
def load_experience_pool():
    """Load all seeded pipeline-solved solutions from disk.
    Returns list of dicts: {task_id, prompt, code, attempts, fname, is_mbpp}.
    Filters out: (a) non-MBPP solutions (live MCP solves), (b) any task that
    happens to be in the test 20 (defense-in-depth on top of seed_memory's anti-cheat).
    """
    # Load test 20 here so we can filter
    test_ids = {line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")}
    pool = []
    # Two patterns: new (MBPP-XXX-Nattempt) and old (in-N-attempt)
    pattern_new = re.compile(r"pipeline-solved-(MBPP-\d+)-(\d+)attempt-(.+)\.md$")
    pattern_old = re.compile(r"pipeline-solved-in-(\d+)-attempt-s-(.+)\.md$")
    for f in os.listdir(CODING_DIR):
        m_new = pattern_new.match(f)
        m_old = None if m_new else pattern_old.match(f)
        if not m_new and not m_old: continue
        # Read content first (needed for both branches)
        try:
            content = open(f"{CODING_DIR}/{f}").read()
        except Exception:
            continue
        m_prompt = re.search(r"\*\*Task:\*\* (.+)", content)
        if not m_prompt: continue
        prompt = m_prompt.group(1).strip()
        m_code = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
        if not m_code: continue
        code = m_code.group(1).strip()
        # Resolve task_id and attempts
        if m_new:
            tid = m_new.group(1).replace("-", "/")
            attempts = int(m_new.group(2))
            is_mbpp = True
        else:
            # Old format: look up task_id from prompt via MBPP corpus
            assert m_old is not None  # guaranteed by the if/else above
            tid = None
            attempts = int(m_old.group(1))
            for mbpp_f in os.listdir(TASKS_DIR):
                if not mbpp_f.startswith("MBPP_"): continue
                try:
                    data = json.load(open(f"{TASKS_DIR}/{mbpp_f}"))
                    if data.get("prompt", "").strip() == prompt.strip():
                        tid = f"MBPP/{mbpp_f.replace('MBPP_','').replace('.json','')}"
                        break
                except Exception:
                    pass
            is_mbpp = tid is not None
        if not is_mbpp: continue  # Skip non-MBPP (live MCP solves like is_prime, is_even)
        if tid in test_ids: continue  # Anti-cheat: never inject a test-20 solution
        pool.append({
            "task_id": tid, "prompt": prompt, "code": code,
            "attempts": attempts, "fname": f
        })
    return pool

def find_best_match(test_prompt, pool, exclude_test_ids):
    """Return the (entry, jaccard_size) with highest overlap, above threshold.
    Excludes any entry whose task_id is in exclude_test_ids (anti-cheat).
    """
    test_tokens = tokenize(test_prompt)
    best = None
    best_size = 0
    for entry in pool:
        if entry["task_id"] in exclude_test_ids: continue
        entry_tokens = tokenize(entry["prompt"])
        size = jaccard_size(test_tokens, entry_tokens)
        if size > best_size:
            best_size = size
            best = entry
    if best is None or best_size < JACCARD_THRESHOLD:
        return None, 0
    return best, best_size

# === MAIN LOOP ===
def main():
    task_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
    print(f"=== PROOF RUN {RUN_NUMBER} — CONDITION B6: FORMAT HINT + EXPERIENCE RECALL ===")
    print(f"  Tasks: {len(task_ids)} (same 20 as B4-local)")
    print(f"  Model: {LLAMA_MODEL}")
    print(f"  Sub-conditions: B4-control (format hint only) and B6-recall (format hint + recall)")
    print(f"  Jaccard threshold: {JACCARD_THRESHOLD} token overlap")
    print()

    # Load experience pool
    pool = load_experience_pool()
    print(f"  Experience pool loaded: {len(pool)} seeded solutions")
    if len(pool) < 5:
        print("  WARNING: pool is very small — recall will rarely fire")
    print()

    # Match log
    match_log_lines = []
    match_log_lines.append(f"B6 Match Log — {datetime.now().isoformat()}")
    match_log_lines.append(f"Pool size: {len(pool)}")
    match_log_lines.append(f"Threshold: {JACCARD_THRESHOLD} token overlap")
    match_log_lines.append("="*80)

    db = sqlite3.connect(DB_PATH)
    passes_b4, passes_b6, fails_b4, fails_b6 = 0, 0, 0, 0
    results = []
    test_id_set = set(task_ids)
    start = time.time()

    for i, task_id in enumerate(task_ids, 1):
        task_file = os.path.join(TASKS_DIR, f"{task_id.replace('/', '_')}.json")
        task = json.load(open(task_file))
        task_prompt = task['prompt']
        func_name, example, test_list = extract_format_hints(task)
        format_hint = build_format_hint(func_name, example, test_list) if func_name else ""

        # ---- B6 RECALL: find best match in pool ----
        match_entry, match_size = find_best_match(task_prompt, pool, test_id_set)
        recall_block = ""
        if match_entry:
            recall_block = f"""PAST SOLUTION (similar task solved before):
Task: {match_entry['prompt']}
```python
{match_entry['code'][:600]}
```

"""
        match_log_lines.append(f"\n[{i:2d}] {task_id}: {task_prompt[:60]}")
        match_log_lines.append(f"      test tokens: {len(tokenize(task_prompt))}")
        if match_entry:
            match_log_lines.append(f"      MATCH: {match_entry['task_id']} (overlap={match_size}) — {match_entry['prompt'][:60]}")
            match_log_lines.append(f"      file: {match_entry['fname']}")
        else:
            match_log_lines.append(f"      NO MATCH (best overlap < {JACCARD_THRESHOLD})")

        # ---- B4-CONTROL attempt ----
        prompt_b4 = f"""FORMAT REQUIREMENTS:
{format_hint}

Write a Python function that solves this problem. Follow the format requirements exactly. Return ONLY the function code in a single markdown code block. Do NOT include the assert tests.

Problem: {task_prompt}

```python
# Your solution here
```"""
        a1_b4, _ = call_gemma(prompt_b4)
        code_b4 = extract_code(a1_b4)
        passed_b4, err_b4 = run_oracle(task, code_b4)
        if passed_b4: passes_b4 += 1
        else: fails_b4 += 1

        # ---- B6-RECALL attempt ----
        prompt_b6 = f"""{recall_block}FORMAT REQUIREMENTS:
{format_hint}

Write a Python function that solves this problem. Follow the format requirements exactly. Return ONLY the function code in a single markdown code block. Do NOT include the assert tests.

Problem: {task_prompt}

```python
# Your solution here
```"""
        a1_b6, _ = call_gemma(prompt_b6)
        code_b6 = extract_code(a1_b6)
        passed_b6, err_b6 = run_oracle(task, code_b6)
        if passed_b6: passes_b6 += 1
        else: fails_b6 += 1

        flip = "FLIP!" if (not passed_b4 and passed_b6) else ("REGRESS!" if (passed_b4 and not passed_b6) else "")
        match_info = f" matched={match_entry['task_id']}({match_size})" if match_entry else " no-match"
        print(f"  [{i:2d}/{len(task_ids)}] {task_id}: B4={'P' if passed_b4 else 'F'} B6={'P' if passed_b6 else 'F'} {flip}{match_info}")

        results.append({
            "task_id": task_id,
            "task_prompt": task_prompt[:80],
            "func_name": func_name,
            "b4_passed": passed_b4, "b4_error": err_b4,
            "b6_passed": passed_b6, "b6_error": err_b6,
            "matched_task_id": match_entry["task_id"] if match_entry else None,
            "match_size": match_size,
            "flip": (not passed_b4 and passed_b6),
            "regress": (passed_b4 and not passed_b6),
        })

    elapsed = time.time() - start
    db.close()

    # Summary
    b4_pct = round(passes_b4 / len(task_ids) * 100, 1)
    b6_pct = round(passes_b6 / len(task_ids) * 100, 1)
    n_flips = sum(1 for r in results if r["flip"])
    n_regress = sum(1 for r in results if r["regress"])
    summary = {
        "condition": "B6 (Format Hint + EXPERIENCE_INDEX recall)",
        "model": LLAMA_MODEL,
        "pool_size": len(pool),
        "timestamp": datetime.now().isoformat(),
        "run_number": RUN_NUMBER,
        "total": len(task_ids),
        "b4_control": {"pass": passes_b4, "fail": fails_b4, "pass_rate": b4_pct},
        "b6_recall":  {"pass": passes_b6, "fail": fails_b6, "pass_rate": b6_pct},
        "n_flips": n_flips, "n_regress": n_regress,
        "total_time_s": round(elapsed, 1),
        "results": results,
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    with open(MATCH_LOG, "w") as f:
        f.write("\n".join(match_log_lines))

    print(f"\n=== CONDITION B6 COMPLETE ===")
    print(f"  B4-control (format hint only):  {passes_b4}/{len(task_ids)} = {b4_pct}%")
    print(f"  B6-recall  (format + recall):  {passes_b6}/{len(task_ids)} = {b6_pct}%")
    print(f"  Flips:   {n_flips}")
    print(f"  Regress: {n_regress}")
    print(f"  Time:    {elapsed:.1f}s")
    print(f"  Saved:   {OUTPUT_FILE}")
    print(f"  Match log: {MATCH_LOG}")
    print(f"\n  Verdict: {'B6 > B4 ✅' if b6_pct > b4_pct else 'B6 <= B4 (no improvement)'}")
    if b6_pct > b4_pct:
        # Identify which stuck tasks flipped
        flips = [r for r in results if r["flip"]]
        print(f"  Flipped tasks: {[r['task_id'] for r in flips]}")

if __name__ == "__main__":
    main()
