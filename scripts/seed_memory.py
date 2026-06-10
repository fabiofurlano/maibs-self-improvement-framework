#!/usr/bin/env python3.10
"""Phase 6 — Step 1: Seed the memory pool with pipeline-only solutions.

Strategy: pick 60 MBPP tasks OUTSIDE the 20-test set. Run the M3 pipeline on each.
Save the agent's actual solution (not canonical_solution) to a detail file.
Append index entry to EXPERIENCE_INDEX.md.

Anti-cheat: refuse any task whose prompt has >= JACCARD_THRESHOLD token overlap
with any test-20 prompt.

Cost: ~$3 M3 cloud usage for 60 tasks (each ~10s).
Output: 60 new detail files + 60 new index lines.
"""
import json, os, sys, time, re, random, requests, sqlite3
from datetime import datetime

# === CONFIG ===
TASKS_DIR = os.path.expanduser("~/.hermes/planning/self-improvement-loop/tasks/mbpp")
PROOF_TASKS = os.path.expanduser("~/.hermes/planning/self-improvement-loop/proof-tasks.txt")
DB_PATH = os.path.expanduser("~/.hermes/planning/self-improvement-loop/experience.db")
REPO_ROOT = "/tmp/maibs-self-improvement-framework"
INDEX_PATH = f"{REPO_ROOT}/experiences/EXPERIENCE_INDEX.md"
CODING_DIR = f"{REPO_ROOT}/experiences/coding"

# M3 endpoint (cloud via OpenRouter)
M3_URL = "https://openrouter.ai/api/v1/chat/completions"

def _get_api_key():
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("OPENROUTER_API_KEY", "")

POOL_SIZE = 60
JACCARD_THRESHOLD = 0.5  # 50% token overlap = potential cheat
SEED_MODEL = "minimax/minimax-m3"
MAX_TOKENS = 800
RUN_SEED = 42
random.seed(RUN_SEED)

# === HELPERS ===
def tokenize(text):
    STOP = {"a","an","the","of","to","in","on","for","and","or","is","it","this","that","with","as","by","at","be","from"}
    return [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP]

def jaccard(a_tokens, b_tokens):
    a, b = set(a_tokens), set(b_tokens)
    if not a or not b: return 0
    return len(a & b) / len(a | b)

def call_m3(prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": SEED_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0
    }
    r = requests.post(M3_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def run_oracle(code, test_setup, test_list):
    full = (test_setup or "") + "\n" + code + "\n" + "\n".join(test_list)
    try:
        ns = {}
        exec(full, ns)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

def extract_code(generation):
    m = re.search(r"```python\s*\n(.*?)```", generation, re.DOTALL)
    if m: return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)```", generation, re.DOTALL)
    if m: return m.group(1).strip()
    return generation.strip()

def build_prompt(task):
    test_list = task.get("test_list", [])
    func_name = None
    example = None
    for test in test_list:
        m = re.match(r"assert\s+(\w+)\(", test.strip())
        if m:
            func_name = m.group(1); break
    for test in test_list:
        m = re.match(r"assert\s+\w+\((.+?)\)\s*==\s*(.+)$", test.strip())
        if m:
            example = (m.group(1).strip(), m.group(2).strip())
            break
    p = f"You are a Python programmer. {task['prompt']}\n\n"
    if func_name:
        p += f"The function must be named `{func_name}`.\n"
    if example:
        args, expected = example
        p += f"Example: `{func_name}({args})` should return `{expected}`.\n"
    p += "\nWrite the function in a single python code block."
    return p

def append_index_line(line):
    with open(INDEX_PATH, "a") as f:
        f.write(line + "\n")

def write_detail_file(tid, prompt, code, attempts, path_taken):
    """Filename uses task_id (deterministic, no collisions)."""
    safe_id = tid.replace("/", "-")
    safe_slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()[:50]).strip("-")
    fname = f"pipeline-solved-{safe_id}-{attempts}attempt-{safe_slug}.md"
    fpath = f"{CODING_DIR}/{fname}"
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = f"""# Pipeline Solve — {today}

**Task:** {prompt}

**Path taken:** {path_taken}

**Solution:**
```python
{code}
```

**Attempts:** {attempts}
"""
    with open(fpath, "w") as f:
        f.write(body)
    return fpath

# === DB WRITE ===
def setup_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seeded_solutions (
            task_id TEXT PRIMARY KEY,
            code TEXT,
            attempts INTEGER,
            passed INTEGER,
            err TEXT,
            seeded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    return db

def log_to_db(db, tid, code, attempts, passed, err=""):
    cur = db.cursor()
    cur.execute("""INSERT OR REPLACE INTO seeded_solutions
        (task_id, code, attempts, passed, err) VALUES (?,?,?,?,?)""",
        (tid, code, attempts, 1 if passed else 0, err))
    db.commit()

# === POOL SELECTION ===
def pick_pool(test_prompts, exclude_seeded, n=POOL_SIZE):
    """Pick n candidate tasks not in test set, not already seeded."""
    test_token_sets = {tid: tokenize(p) for tid, p in test_prompts.items()}
    all_files = sorted([f for f in os.listdir(TASKS_DIR) if f.startswith("MBPP_") and f.endswith(".json")])
    candidates = []
    for fname in all_files:
        num = fname.replace("MBPP_", "").replace(".json", "")
        tid = f"MBPP/{num}"
        if tid in test_prompts or tid in exclude_seeded:
            continue
        with open(f"{TASKS_DIR}/{fname}") as f:
            data = json.load(f)
        prompt = data.get("prompt", "")
        if not prompt: continue
        p_tokens = tokenize(prompt)
        cheat = any(jaccard(p_tokens, t) > JACCARD_THRESHOLD for t in test_token_sets.values())
        if cheat: continue
        candidates.append((tid, data))
    print(f"[seed] {len(candidates)} candidates pass anti-cheat, {len(exclude_seeded)} already seeded")
    random.shuffle(candidates)
    return candidates[:n]

# === MAIN ===
def main():
    global API_KEY
    API_KEY = _get_api_key()
    if not API_KEY:
        print("ERROR: OPENROUTER_API_KEY not found", file=sys.stderr); sys.exit(1)

    # Load test 20
    test_ids = [line.strip() for line in open(PROOF_TASKS) if line.strip().startswith("MBPP/")]
    test_prompts = {}
    for tid in test_ids:
        num = tid.split("/")[1]
        path = f"{TASKS_DIR}/MBPP_{num}.json"
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            test_prompts[tid] = data["prompt"]
    print(f"[seed] Test 20 loaded: {len(test_prompts)} prompts")

    # Setup DB, find already-seeded task_ids
    db = setup_db()
    cur = db.execute("SELECT task_id FROM seeded_solutions")
    already_seeded = {r[0] for r in cur.fetchall()}
    print(f"[seed] Already seeded: {len(already_seeded)} tasks")

    # Pick pool
    pool = pick_pool(test_prompts, already_seeded, n=POOL_SIZE)
    if not pool:
        print("[seed] No new candidates — done")
        return
    print(f"[seed] Will run on {len(pool)} new tasks")

    # Run pipeline
    print(f"\n[seed] Starting pipeline on {len(pool)} tasks...")
    results = []
    seeded = 0
    for i, (tid, task) in enumerate(pool, 1):
        prompt_str = task["prompt"]
        test_list = task.get("test_list", [])
        test_setup = task.get("test_setup_code", "")
        p = build_prompt(task)
        attempts = 0
        passed = False
        final_code = ""
        err = ""
        path = ""
        for attempt in range(1, 4):
            attempts = attempt
            try:
                gen = call_m3(p)
                code = extract_code(gen)
                passed, err = run_oracle(code, test_setup, test_list)
                if passed:
                    final_code = code
                    path = f"attempt_{attempt}_pass"
                    break
                else:
                    p += f"\n\nYour previous attempt failed with: {err}\nPlease fix."
                    path = f"attempt_{attempt}_fail"
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                path = f"attempt_{attempt}_error"
        log_to_db(db, tid, final_code, attempts, passed, err)
        status = "PASS" if passed else "FAIL"
        print(f"  [{i:2d}/{len(pool)}] {tid}: {status} ({attempts} attempts) {err[:50] if err else ''}")
        results.append({
            "task_id": tid, "passed": passed, "attempts": attempts, "err": err
        })
        if passed:
            write_detail_file(tid, prompt_str, final_code, attempts, path)
            summary = f"pipeline solved in {attempts} attempt(s): {prompt_str[:80]}"
            index_line = f"| `[solution]` | coding | {datetime.now().strftime('%Y-%m-%d')} | {summary} |"
            append_index_line(index_line)
            seeded += 1
        time.sleep(0.3)

    db.close()

    # Summary
    n_pass = sum(1 for r in results if r["passed"])
    print(f"\n[seed] DONE: {n_pass}/{len(pool)} passed, {seeded} detail files + index lines written")
    out_json = f"{REPO_ROOT}/results/seed-B6.json"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w") as f:
        json.dump({
            "pool_size": len(pool),
            "n_pass": n_pass,
            "n_seed_written": seeded,
            "results": results,
            "anti_cheat_threshold": JACCARD_THRESHOLD,
            "run_at": datetime.now().isoformat()
        }, f, indent=2)
    print(f"[seed] Summary: {out_json}")

if __name__ == "__main__":
    main()
