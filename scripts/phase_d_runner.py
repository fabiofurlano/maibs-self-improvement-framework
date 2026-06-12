#!/usr/bin/env python3.10
"""Phase D Proof Test — Gemma+pipeline vs Frontier bare on web scraper task."""

import sys, os, json, time, subprocess, traceback
sys.path.insert(0, '/tmp/maibs-self-improvement-framework')

TASK = (
    "Build a working web scraper: fetch a public webpage using requests, "
    "extract all hyperlinks using BeautifulSoup, filter to external links only, "
    "write results to a CSV file, include error handling for bad URLs, "
    "write a usage README."
)

CRITERIA = [
    "Uses requests library correctly",
    "Uses BeautifulSoup to parse HTML",
    "Filters external links only (not internal)",
    "Writes to CSV correctly",
    "Error handling for bad URLs present",
    "README exists and is accurate",
]

RESULTS_DIR = "/tmp/maibs-self-improvement-framework/projects/maibs"
os.makedirs(RESULTS_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# RUN 1 — Gemma + full pipeline via solve_multistep()
# ─────────────────────────────────────────────
print("=" * 70)
print("PHASE D — RUN 1: Gemma E4B + full pipeline via solve_multistep()")
print(f"Task: {TASK[:120]}...")
print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

t0 = time.time()
try:
    from maibs_mcp_server import solve_multistep
    criteria_text = "\n".join(f"- {c}" for c in CRITERIA)
    run1_result = solve_multistep(TASK, task_type="coding", original_criteria=criteria_text)
    run1_elapsed = time.time() - t0
    print(f"\nRun 1 elapsed: {run1_elapsed:.0f}s ({run1_elapsed/60:.1f}m)")
    print(f"Run 1 passed: {run1_result.get('passed')}")
    print(f"Steps completed: {run1_result.get('completed_steps', '?')}/{run1_result.get('total_steps', '?')}")
except Exception as e:
    run1_elapsed = time.time() - t0
    run1_result = {"error": str(e), "traceback": traceback.format_exc()}
    print(f"\nRun 1 FAILED after {run1_elapsed:.0f}s: {e}")

# ─────────────────────────────────────────────
# RUN 2 — Frontier bare (DeepSeek V4 Pro, one prompt, no tools)
# ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("PHASE D — RUN 2: DeepSeek V4 Pro bare (single prompt, no tools)")
print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

import urllib.request, urllib.error

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not API_KEY:
    # Try .env
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

t0 = time.time()
try:
    payload = json.dumps({
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a senior Python engineer. Write complete, production-quality code. Output ALL files needed. Do not skip error handling or the README."},
            {"role": "user", "content": f"""Build a working web scraper with these requirements:

1. Fetch a public webpage using the `requests` library (include User-Agent header)
2. Parse the HTML with `BeautifulSoup` from bs4
3. Extract all hyperlinks (<a href="...">)
4. Filter to EXTERNAL links only (different domain from the target URL)
5. Write filtered results to a CSV file with columns: url, link_text, target_url
6. Include error handling: bad URLs (timeout, connection error), missing pages (404), non-HTML responses
7. Write a usage README.md with install instructions, usage example, and output format

Write ALL the code in a single Python script `scraper.py` plus a `README.md`. Use argparse for the URL parameter. Output everything now."""}
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "MAIBS-PhaseD",
        }
    )

    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read().decode("utf-8"))
    run2_elapsed = time.time() - t0

    run2_raw = data["choices"][0]["message"]["content"]
    run2_tokens = data.get("usage", {})
    run2_result = {
        "raw_output": run2_raw,
        "tokens": run2_tokens,
        "model": data.get("model", "unknown"),
    }
    print(f"\nRun 2 elapsed: {run2_elapsed:.0f}s")
    print(f"Run 2 tokens: {run2_tokens}")
    print(f"Run 2 model: {data.get('model')}")
except Exception as e:
    run2_elapsed = time.time() - t0
    run2_result = {"error": str(e), "traceback": traceback.format_exc()}
    print(f"\nRun 2 FAILED after {run2_elapsed:.0f}s: {e}")

# ─────────────────────────────────────────────
# SAVE RAW RESULTS
# ─────────────────────────────────────────────
raw = {
    "task": TASK,
    "criteria": CRITERIA,
    "run1_gemma_pipeline": {
        "elapsed_s": run1_elapsed,
        "result": run1_result,
    },
    "run2_frontier_bare": {
        "elapsed_s": run2_elapsed,
        "result": run2_result,
    },
}

raw_path = os.path.join(RESULTS_DIR, "phase-d-raw.json")
with open(raw_path, "w") as f:
    json.dump(raw, f, indent=2, default=str)

print(f"\nRaw results saved to {raw_path}")
print("Done.")
