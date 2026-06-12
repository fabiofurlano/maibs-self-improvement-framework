#!/usr/bin/env python3.10
"""Phase D Run 1 — Gemma + full pipeline. Logs every step."""

import sys, os, json, time, traceback
sys.path.insert(0, '/tmp/maibs-self-improvement-framework')
from maibs_mcp_server import solve_multistep

TASK = (
    "Build a working web scraper: fetch a public webpage using requests, "
    "extract all hyperlinks using BeautifulSoup, filter to external links only, "
    "write results to a CSV file, include error handling for bad URLs, "
    "write a usage README."
)

RESULTS_DIR = "/tmp/maibs-self-improvement-framework/projects/maibs"
os.makedirs(RESULTS_DIR, exist_ok=True)

print("=" * 70, flush=True)
print("PHASE D — RUN 1: Gemma E4B + full pipeline via solve_multistep()", flush=True)
print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print("=" * 70, flush=True)

t0 = time.time()
try:
    result = solve_multistep(TASK)
    elapsed = time.time() - t0

    # Extract step details
    steps_data = result.get("steps", [])
    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)
    print(f"All passed: {result.get('passed')}", flush=True)
    print(f"Completed: {result.get('completed_steps')}/{result.get('total_steps')}", flush=True)
    print(f"Path: {' → '.join(result.get('path_taken', []))}", flush=True)

    for i, s in enumerate(steps_data):
        print(f"\n  Step {i+1}: {'✅' if s.get('passed') else '❌'}", flush=True)
        print(f"    Goal: {s.get('goal', '?')[:100]}", flush=True)
        print(f"    Context: {s.get('context_size', '?')} chars", flush=True)
        print(f"    Evaluator: {s.get('evaluator_reason', '?')[:120]}", flush=True)
        print(f"    Logs: {s.get('logs', [])}", flush=True)

    # Save raw
    raw_path = os.path.join(RESULTS_DIR, "phase-d-run1-raw.json")
    with open(raw_path, "w") as f:
        json.dump({
            "task": TASK,
            "elapsed_s": elapsed,
            "passed": result.get("passed"),
            "path_taken": result.get("path_taken", []),
            "completed_steps": result.get("completed_steps"),
            "total_steps": result.get("total_steps"),
            "steps": steps_data,
        }, f, indent=2, default=str)
    print(f"\nRaw saved to {raw_path}", flush=True)

except Exception as e:
    elapsed = time.time() - t0
    print(f"\nFAILED after {elapsed:.0f}s: {e}", flush=True)
    traceback.print_exc()
