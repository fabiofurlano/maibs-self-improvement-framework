#!/usr/bin/env python3.10
"""Phase C Gate Test — Orchestrator Loop

Tests solve_multistep() end-to-end with a 3-step task.
Gate criteria:
  - All 3 steps complete (passed == True on each step)
  - Evaluator catches at least one mid-step violation
  - Context stays under 4K tokens at every step
  - DeepSeek V4 Pro plans steps, Gemma executes each one
"""

import sys, os, json, time

# Point to the repo so we can import from it
REPO = "/tmp/maibs-self-improvement-framework"
sys.path.insert(0, REPO)

# Import solve_multistep — the module-level FastAPI app won't start the server
from maibs_mcp_server import solve_multistep

# ── Task ─────────────────────────────────────────────────
# "Write a function that downloads a file using requests with progress tracking"
# This is a 3-step task that exercises: web search → function building → testing
# Planted criteria: DeepSeek will generate criteria; we verify the evaluator works
# by checking that any step failing its criteria is caught.

TASK = """Build a Python utility to download a file from a URL with progress reporting.

The utility should:
1. First, use web search to find what HTTP status code means "partial content" (needed for resume support)
2. Write a function download_file(url, dest_path) that uses the requests library to download a file
3. Write a test for download_file that verifies it handles HTTP errors correctly

Each step should produce working, runnable Python code."""

# ── Run ──────────────────────────────────────────────────
print("=" * 60)
print("Phase C Gate Test — Orchestrator Loop")
print("=" * 60)
print(f"\nTask: {TASK[:120]}...")
print()

t0 = time.time()
result = solve_multistep(TASK, task_type="coding")
elapsed = time.time() - t0

# ── Print results ────────────────────────────────────────
print(f"\n{'='*60}")
print(f"RESULTS (elapsed: {elapsed:.0f}s)")
print(f"{'='*60}")

print(f"\nPassed: {result['passed']}")
print(f"Total steps planned: {result['total_steps']}")
print(f"Steps completed: {result['completed_steps']}")
print(f"Path taken: {' → '.join(result['path_taken'])}")

if result['error']:
    print(f"Error: {result['error']}")

print(f"\n{'─'*60}")
print("PER-STEP DETAILS")
print(f"{'─'*60}")

violations_caught = 0
all_context_ok = True

for step in result['steps']:
    sn = step['step']
    print(f"\nStep {sn}: {step.get('goal', 'N/A')[:80]}")
    print(f"  Passed: {step['passed']}")
    print(f"  Context: {step['context_size']} chars")
    print(f"  Evaluator: {step.get('evaluator_reason', 'N/A')[:100]}")
    
    if step['logs']:
        for log in step['logs'][:6]:
            print(f"    {log}")
    
    # Track violations
    if not step['passed'] and step.get('evaluator_reason', ''):
        violations_caught += 1
    
    # Context check
    if step['context_size'] > 4000:
        all_context_ok = False
        print(f"  ⚠️  CONTEXT OVER 4K!")

# ── Gate verdict ─────────────────────────────────────────
print(f"\n{'='*60}")
print("GATE VERDICT")
print(f"{'='*60}")

checks = []

# Check 1: All steps complete
all_steps_pass = result['passed'] and result['completed_steps'] == result['total_steps']
checks.append(("All steps complete", all_steps_pass, 
    f"{result['completed_steps']}/{result['total_steps']} steps passed"))

# Check 2: At least one evaluator violation caught
# (A "planted" error = any criterion the model missed that the evaluator caught)
violation_found = violations_caught > 0
checks.append(("Evaluator caught ≥1 violation", violation_found,
    f"{violations_caught} violation(s) caught"))

# Check 3: Context under 4K at every step
checks.append(("Context ≤4K every step", all_context_ok,
    f"Max: {max((s['context_size'] for s in result['steps']), default=0)} chars"))

# Check 4: Orchestrator planned steps
steps_planned = result['total_steps'] >= 3
checks.append(("Orchestrator planned ≥3 steps", steps_planned,
    f"{result['total_steps']} steps planned"))

# Check 5: Pipeline ran — we have results
pipeline_ran = len(result['steps']) > 0
checks.append(("Pipeline executed", pipeline_ran,
    f"{len(result['steps'])} step results returned"))

print()
all_pass = True
for name, passed, detail in checks:
    status = "✅" if passed else "❌"
    if not passed:
        all_pass = False
    print(f"  {status} {name}: {detail}")

print(f"\n{'─'*60}")
if all_pass:
    print("GATE: ✅ PASS")
else:
    print("GATE: ❌ FAIL")
print(f"{'─'*60}")

# ── Save raw results ─────────────────────────────────────
out_path = REPO + "/projects/maibs/phase-c-orchestrator-results-raw.json"
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w') as f:
    json.dump({
        "task": TASK,
        "elapsed_s": round(elapsed, 1),
        "passed": result['passed'],
        "total_steps": result['total_steps'],
        "completed_steps": result['completed_steps'],
        "path_taken": result['path_taken'],
        "error": result['error'],
        "steps": result['steps'],
        "gate_checks": {name: {"passed": p, "detail": d} for name, p, d in checks},
        "gate_passed": all_pass
    }, f, indent=2)

print(f"\nRaw results saved: {out_path}")
