#!/usr/bin/env python3.10
"""Phase D2 Proof Test — Gemma+pipeline WITH integration manifest + final product eval.
Same task as Phase D. DeepSeek baseline from Phase D stands (no rerun needed)."""

import sys, os, json, time, traceback
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

print("=" * 70)
print("PHASE D2 — Gemma E4B + pipeline (integration manifest + final eval)")
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
    print(f"Manifest sizes: {run1_result.get('manifest_sizes', [])}")
    print(f"Final product eval: {run1_result.get('final_product_eval', {})}")
    print(f"Path: {' → '.join(run1_result.get('path_taken', []))}")
    
    # Print per-step details
    for step in run1_result.get('steps', []):
        print(f"\n  Step {step['step']}: {step['goal'][:80]}")
        print(f"    Passed: {step['passed']}, Context: {step['context_size']} chars")
        print(f"    Eval: {step['evaluator_reason'][:100] if step['evaluator_reason'] else 'N/A'}")
    
    if run1_result.get('failed_steps'):
        for fs in run1_result['failed_steps']:
            print(f"\n  FAILED Step {fs['step']}: {fs['goal'][:80]}")
            print(f"    Reason: {fs['reason'][:200]}")

except Exception as e:
    run1_elapsed = time.time() - t0
    run1_result = {"error": str(e), "traceback": traceback.format_exc()}
    print(f"\nRun 1 FAILED after {run1_elapsed:.0f}s: {e}")

# Save raw results
raw = {
    "task": TASK,
    "criteria": CRITERIA,
    "run1_gemma_pipeline": {
        "elapsed_s": run1_elapsed,
        "result": run1_result,
    },
    "meta": {
        "phase": "D2",
        "fixes": ["integration_manifest", "final_product_eval"],
        "ctx_size": 16384,
        "build": "b9586",
        "model": "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf",
    }
}

raw_path = os.path.join(RESULTS_DIR, "phase-d2-raw.json")
with open(raw_path, "w") as f:
    json.dump(raw, f, indent=2, default=str)

print(f"\nRaw results saved to {raw_path}")
print("Done.")
