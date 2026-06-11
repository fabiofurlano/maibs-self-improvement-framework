#!/usr/bin/env python3.10
"""Phase D Run 1 — Manual step-by-step pipeline with visibility at every phase."""

import sys, os, json, time, traceback
sys.path.insert(0, '/tmp/maibs-self-improvement-framework')

from maibs_mcp_server import classify_intent, safety_gate, _plan_steps, _execute_step

TASK = (
    "Build a working web scraper: fetch a public webpage using requests, "
    "extract all hyperlinks using BeautifulSoup, filter to external links only, "
    "write results to a CSV file, include error handling for bad URLs, "
    "write a usage README."
)

RESULTS_DIR = "/tmp/maibs-self-improvement-framework/projects/maibs"
os.makedirs(RESULTS_DIR, exist_ok=True)

TS = lambda: time.strftime('%H:%M:%S')
t0 = time.time()

print("=" * 70, flush=True)
print(f"[{TS()}] PHASE D RUN 1 — Manual step-by-step pipeline", flush=True)
print("=" * 70, flush=True)

# ── Phase 1: Classify ──
print(f"\n[{TS()}] ── CLASSIFY INTENT ──", flush=True)
try:
    c0 = time.time()
    intent = classify_intent(TASK)
    print(f"[{TS()}] intent = {intent} ({time.time()-c0:.1f}s)", flush=True)
except Exception as e:
    intent = "execute"
    print(f"[{TS()}] classify FAILED: {e}", flush=True)

# ── Phase 2: Safety Gate ──
print(f"\n[{TS()}] ── SAFETY GATE ──", flush=True)
try:
    c0 = time.time()
    go, reason = safety_gate(TASK)
    print(f"[{TS()}] go={go} reason={reason[:80]} ({time.time()-c0:.1f}s)", flush=True)
    if not go:
        print(f"BLOCKED: {reason}", flush=True)
        sys.exit(1)
except Exception as e:
    print(f"[{TS()}] safety FAILED: {e}", flush=True)
    sys.exit(1)

# ── Phase 3: Plan Steps (DeepSeek cloud) ──
print(f"\n[{TS()}] ── PLAN STEPS (DeepSeek cloud) ──", flush=True)
try:
    c0 = time.time()
    steps, err = _plan_steps(TASK)
    elapsed = time.time() - c0
    print(f"[{TS()}] plan: {len(steps)} steps, err={err[:100] if err else 'none'} ({elapsed:.1f}s)", flush=True)
    if err:
        print(f"PLAN ERROR: {err}", flush=True)
        sys.exit(1)
    for i, s in enumerate(steps):
        print(f"  Step {i+1}: {s['goal'][:100]}")
        print(f"    Criteria: {s.get('criteria', [])}")
except Exception as e:
    print(f"[{TS()}] plan FAILED: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

# ── Phase 4: Execute Steps ──
print(f"\n[{TS()}] ── EXECUTE {len(steps)} STEPS ──", flush=True)
step_results = []
previous_context = ""
all_passed = True
failed_steps = []

for i, step in enumerate(steps):
    print(f"\n  [{TS()}] >>> STEP {i+1}/{len(steps)} <<<", flush=True)
    print(f"  Goal: {step['goal'][:120]}", flush=True)

    try:
        c0 = time.time()
        result = _execute_step(step, TASK, previous_context, i, len(steps))
        elapsed = time.time() - c0

        step_results.append(result)
        status = "✅" if result.get("passed") else "❌"
        print(f"  [{TS()}] {status} passed={result.get('passed')} ctx={result.get('context_size')} ({elapsed:.0f}s)", flush=True)
        print(f"    Iterations: {len(result.get('logs', []))}", flush=True)
        print(f"    Evaluator: {result.get('evaluator_reason', '')[:120]}", flush=True)
        print(f"    Logs: {result.get('logs', [])}", flush=True)

        if result.get("passed"):
            previous_context = result.get("compressed_context", "")
        else:
            all_passed = False
            failed_steps.append({"step": i+1, "goal": step["goal"], "reason": result.get("evaluator_reason")})
            print(f"    ❌ FAILED — continuing to next step", flush=True)

    except Exception as e:
        print(f"  [{TS()}] EXCEPTION: {e}", flush=True)
        traceback.print_exc()
        all_passed = False
        failed_steps.append({"step": i+1, "goal": step["goal"], "reason": str(e)})

# ── Summary ──
total_elapsed = time.time() - t0
print(f"\n{'='*70}", flush=True)
print(f"[{TS()}] SUMMARY — {total_elapsed:.0f}s ({total_elapsed/60:.1f}m)", flush=True)
print(f"All passed: {all_passed}", flush=True)
print(f"Completed: {len(step_results)}/{len(steps)} steps", flush=True)
if failed_steps:
    print(f"FAILED STEPS: {json.dumps(failed_steps, indent=2)}", flush=True)

for i, r in enumerate(step_results):
    print(f"  Step {i+1}: {'PASS' if r.get('passed') else 'FAIL'} ctx={r.get('context_size','?')} logs={r.get('logs',[])}", flush=True)

# ── Save ──
save_path = os.path.join(RESULTS_DIR, "phase-d-run1-raw.json")
with open(save_path, "w") as f:
    json.dump({
        "task": TASK,
        "elapsed_s": total_elapsed,
        "all_passed": all_passed,
        "total_steps": len(steps),
        "completed_steps": len(step_results),
        "failed_steps": failed_steps,
        "steps": step_results,
    }, f, indent=2, default=str)
print(f"\nSaved to {save_path}", flush=True)
