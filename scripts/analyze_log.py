#!/usr/bin/env python3
"""Analyze llama-server log to break down 97 Phase D2 calls by type."""

import re, sys
from collections import defaultdict

LOG = "/home/fabio/.hermes/logs/llama-server.log"

tasks = {}  # task_id -> {start, release_tokens, is_child}

with open(LOG) as f:
    for line in f:
        # Task launch
        m = re.search(r'task (\d+) \| processing task, is_child = (\d+)', line)
        if m:
            tid = int(m.group(1))
            is_child = int(m.group(2))
            ts = float(line.split()[0].replace('.', '').lstrip('0') or '0')
            tasks[tid] = {'start': line.strip()[:80], 'is_child': is_child, 'release_tokens': 0, 'has_gen': False}
            continue
        
        # Task release
        m = re.search(r'task (\d+) \| stop processing: n_tokens = (\d+)', line)
        if m:
            tid = int(m.group(1))
            ntoks = int(m.group(2))
            if tid in tasks:
                tasks[tid]['release_tokens'] = ntoks
        
        # Generation marker
        m = re.search(r'task (\d+) \| n_decoded', line)
        if m:
            tid = int(m.group(1))
            if tid in tasks:
                tasks[tid]['has_gen'] = True

# Categorize by total tokens
cats = defaultdict(int)
sizes = []
for tid, t in tasks.items():
    nt = t['release_tokens']
    sizes.append(nt)
    if nt == 0:
        cats['no_release_data'] += 1
    elif nt <= 100:
        cats['tiny_(classifier/safety)'] += 1
    elif nt <= 400:
        cats['medium_(evaluator)'] += 1
    elif nt <= 800:
        cats['medium_large_(compressor)'] += 1
    elif nt <= 2000:
        cats['large_(solver)'] += 1
    else:
        cats['extra_large_(very_long_solve)'] += 1

print("=" * 60)
print("CALL BREAKDOWN BY SIZE (total tokens = prompt + generated)")
print("=" * 60)
for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {count}")

print(f"\n  TOTAL TASKS: {len(tasks)}")
print(f"  Tasks with generation: {sum(1 for t in tasks.values() if t['has_gen'])}")
print(f"  Tasks without generation: {sum(1 for t in tasks.values() if not t['has_gen'])}")

# Sort by task_id to see the sequence
print("\n" + "=" * 60)
print("SEQUENCE (task_id → total_tokens → category)")
print("=" * 60)

sorted_tasks = sorted(tasks.items(), key=lambda x: x[0])
prev_cat = None
step_num = 0
seq = []

for tid, t in sorted_tasks:
    nt = t['release_tokens']
    gen = "GEN" if t['has_gen'] else "NOGEN"
    if nt <= 100:
        cat = "TINY"
    elif nt <= 400:
        cat = "MED"
    elif nt <= 800:
        cat = "MED-LG"
    elif nt <= 2000:
        cat = "LARGE"
    else:
        cat = "XLARGE"
    
    # Detect step boundaries: a LARGE call followed by MED (evaluator) = a solve+evaluate pair
    # Multiple LARGE calls in a row = retries
    seq.append((tid, nt, cat, gen))
    if nt > 0:
        print(f"  task {tid:5d}: {nt:5d} total_toks [{cat:6s}] {gen}")

# Now identify retry patterns
print("\n" + "=" * 60)
print("RETRY PATTERN ANALYSIS")
print("=" * 60)

# A solver call is LARGE or XLARGE
# An evaluator call is MED
# A retry is a LARGE call that follows a MED call (evaluator rejected previous attempt)

retries = 0
solver_calls = 0
evaluator_calls = 0
compressor_calls = 0
tiny_calls = 0

current_step_solvers = 0
step_solver_counts = []
in_step = False

for i, (tid, nt, cat, gen) in enumerate(seq):
    if cat == 'TINY':
        tiny_calls += 1
    elif cat == 'MED':
        evaluator_calls += 1
    elif cat == 'MED-LG':
        compressor_calls += 1
    elif cat in ('LARGE', 'XLARGE'):
        solver_calls += 1
        if in_step:
            current_step_solvers += 1
        else:
            current_step_solvers = 1
            in_step = True
    else:
        # no_release — skip
        pass
    
    # Detect step boundary: compressor or tiny after a solver chain
    if cat in ('MED-LG', 'TINY') and in_step and current_step_solvers > 0:
        step_solver_counts.append(current_step_solvers)
        current_step_solvers = 0
        in_step = False

# Catch last step
if current_step_solvers > 0:
    step_solver_counts.append(current_step_solvers)

print(f"  Solver (LARGE) calls: {solver_calls}")
print(f"  Evaluator (MED) calls: {evaluator_calls}")
print(f"  Compressor (MED-LG) calls: {compressor_calls}")
print(f"  Tiny calls (classifier/safety): {tiny_calls}")
print(f"  No-release-data calls: {len(tasks) - solver_calls - evaluator_calls - compressor_calls - tiny_calls}")

print(f"\n  Solver calls per step: {step_solver_counts}")
if step_solver_counts:
    print(f"  Max solver calls in one step: {max(step_solver_counts)}")
    print(f"  Steps with >3 solver calls: {sum(1 for s in step_solver_counts if s > 3)}")

# Check: is 3-retry limit enforced?
print("\n" + "=" * 60)
print("3-RETRY LIMIT CHECK")
print("=" * 60)
violations = [s for s in step_solver_counts if s > 3]
if violations:
    print(f"  ❌ VIOLATIONS FOUND: steps with {violations} solver attempts")
    print(f"  The 3-retry limit is NOT being enforced in practice")
else:
    print(f"  ✅ All steps have ≤3 solver calls: {step_solver_counts}")
    print(f"  The 3-retry limit appears to be working")
