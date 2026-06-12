#!/usr/bin/env python3
"""Refined Phase D2 log analysis — distinguish evaluator (large prompt, NOGEN/short output) from solver (large prompt, GEN)."""

import re
from collections import defaultdict

LOG = "/home/fabio/.hermes/logs/llama-server.log"

tasks = {}
with open(LOG) as f:
    for line in f:
        m = re.search(r'task (\d+) \| processing task, is_child = (\d+)', line)
        if m:
            tid = int(m.group(1))
            tasks[tid] = {'release_tokens': 0, 'has_gen': False, 'n_decoded_max': 0}
            continue
        m = re.search(r'task (\d+) \| stop processing: n_tokens = (\d+)', line)
        if m:
            tid = int(m.group(1))
            if tid in tasks:
                tasks[tid]['release_tokens'] = int(m.group(2))
        m = re.search(r'task (\d+) \| n_decoded = +(\d+)', line)
        if m:
            tid = int(m.group(1))
            nd = int(m.group(2))
            if tid in tasks:
                tasks[tid]['has_gen'] = True
                tasks[tid]['n_decoded_max'] = max(tasks[tid]['n_decoded_max'], nd)

# Categorize
CLASSIFIER_SAFETY = 0
EVALUATOR = 0
COMPRESSOR = 0
SOLVER = 0
UNKNOWN = 0

sorted_tasks = sorted(tasks.items(), key=lambda x: x[0])
seq = []

for tid, t in sorted_tasks:
    nt = t['release_tokens']
    gen = t['has_gen']
    nd = t['n_decoded_max']
    
    if nt == 0:
        cat = "NO_DATA"
        UNKNOWN += 1
    elif nt <= 100:
        cat = "CLASSIFIER/SAFETY"
        CLASSIFIER_SAFETY += 1
    elif not gen and nd == 0 and nt > 400:
        # Large prompt, NO generation tokens logged = evaluator (big code + short verdict)
        cat = "EVALUATOR"
        EVALUATOR += 1
    elif not gen and nt > 100:
        # Medium prompt, no gen = could be evaluator (short output) or compressor
        if nt <= 400:
            cat = "EVALUATOR (short)"
            EVALUATOR += 1
        else:
            cat = "COMPRESSOR"
            COMPRESSOR += 1
    elif gen and nd < 30:
        # Generated very few tokens = evaluator with brief output
        cat = "EVALUATOR"
        EVALUATOR += 1
    elif gen and nd >= 30:
        # Generated substantial tokens = solver or compressor
        if nt <= 500:
            cat = "COMPRESSOR"
            COMPRESSOR += 1
        else:
            cat = "SOLVER"
            SOLVER += 1
    else:
        cat = f"OTHER (nt={nt}, gen={gen}, nd={nd})"
        UNKNOWN += 1
    
    seq.append((tid, nt, nd, gen, cat))

print("=" * 60)
print("REFINED CALL BREAKDOWN")
print("=" * 60)
print(f"  CLASSIFIER/SAFETY: {CLASSIFIER_SAFETY}")
print(f"  EVALUATOR:         {EVALUATOR}")
print(f"  COMPRESSOR:        {COMPRESSOR}")
print(f"  SOLVER:            {SOLVER}")
print(f"  UNKNOWN:           {UNKNOWN}")
print(f"  TOTAL:             {len(tasks)}")

# Per-step analysis: group solver+evaluator pairs
print("\n" + "=" * 60)
print("STEP-BY-STEP RETRY ANALYSIS")
print("=" * 60)

steps = []
current_step = None

for tid, nt, nd, gen, cat in seq:
    if cat == "SOLVER":
        if current_step is None:
            current_step = {'solvers': 0, 'evaluators': 0, 'compressors': 0, 'tasks': []}
            steps.append(current_step)
        current_step['solvers'] += 1
        current_step['tasks'].append(f"solve({tid}:{nt}t)")
    elif cat.startswith("EVALUATOR"):
        if current_step is None:
            current_step = {'solvers': 0, 'evaluators': 0, 'compressors': 0, 'tasks': []}
            steps.append(current_step)
        current_step['evaluators'] += 1
        current_step['tasks'].append(f"eval({tid}:{nt}t)")
    elif cat == "COMPRESSOR":
        if current_step:
            current_step['compressors'] += 1
            current_step['tasks'].append(f"compress({tid}:{nt}t)")
    # CLASSIFIER/SAFETY don't end steps

for i, s in enumerate(steps):
    solvers = s['solvers']
    evals = s['evaluators']
    comps = s['compressors']
    retries = max(0, solvers - 1)  # first solve isn't a retry
    evals_per_solve = evals / max(solvers, 1)
    
    flag = "❌ EXCEEDS 3" if retries > 2 else "✅"
    print(f"  Step {i+1}: {solvers} solver calls, {evals} evaluator calls, {comps} compressors — {retries} retries {flag}")
    print(f"    Tasks: {' | '.join(s['tasks'])}")

# Summary
print("\n" + "=" * 60)
print("VERDICT")
print("=" * 60)
violations = [s for s in steps if s['solvers'] > 3]
if violations:
    print(f"  ❌ {len(violations)}/{len(steps)} steps exceed 3 solver attempts")
    for i, s in enumerate(steps):
        if s['solvers'] > 3:
            print(f"     Step {i+1}: {s['solvers']} solver calls")
    print(f"\n  ROOT CAUSE: The 3-retry limit exists in code (MAX_ITERATIONS_PER_STEP=3)")
    print(f"  but the limit checks the LOOP ITERATION count, not the number of SOLVER calls.")
    print(f"  If a solver produces code that passes the oracle (no syntax errors)")
    print(f"  but fails the evaluator, it eats one iteration. After 3 iterations,")
    print(f"  the reasoning lifeline kicks in — which triggers ANOTHER solver call.")
    print(f"  AND the lifeline's output also gets evaluated — if that fails, the")
    print(f"  step is supposed to stop. But if the pipeline mis-detects 'passed'...")
else:
    print(f"  ✅ All steps within 3 solver attempts")
