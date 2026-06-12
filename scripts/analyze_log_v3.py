#!/usr/bin/env python3
"""Phase D2 — fix classification: distinguish solver (long gen) from evaluator (large prompt, short gen)."""

import re
from collections import defaultdict

LOG = "/home/fabio/.hermes/logs/llama-server.log"

tasks = {}
with open(LOG) as f:
    for line in f:
        m = re.search(r'task (\d+) \| processing task, is_child = (\d+)', line)
        if m:
            tid = int(m.group(1))
            tasks[tid] = {'release_tokens': 0, 'n_decoded_max': 0, 'gen_logs': 0}
            continue
        m = re.search(r'task (\d+) \| stop processing: n_tokens = (\d+)', line)
        if m:
            tid = int(m.group(1))
            if tid in tasks:
                tasks[tid]['release_tokens'] = int(m.group(2))
        m = re.search(r'task (\d+) \| n_decoded = +(\d+),', line)
        if m:
            tid = int(m.group(1))
            nd = int(m.group(2))
            if tid in tasks:
                tasks[tid]['n_decoded_max'] = max(tasks[tid]['n_decoded_max'], nd)
                tasks[tid]['gen_logs'] += 1  # count timing log entries

# Classification by generation output size
# Solver: generates 100+ tokens of code → many gen_logs entries
# Evaluator: generates 5-50 tokens of verdict → 0-1 gen_log entries (short)
# Compressor: generates 20-80 tokens → 1-2 gen_log entries
CLASSIFIER = 0
EVALUATOR = 0 
COMPRESSOR = 0
SOLVER = 0
UNKNOWN = 0

for tid, t in sorted(tasks.items(), key=lambda x: x[0]):
    nt = t['release_tokens']
    nd = t['n_decoded_max']
    gl = t['gen_logs']
    
    if nt == 0:
        UNKNOWN += 1
        continue
    
    # Estimate generation tokens from log entries
    # Each timing entry is ~17-20 tokens (varies). Use n_decoded_max as best estimate
    gen_tokens = nd if nd > 0 else 0
    
    if nt <= 100:
        CLASSIFIER += 1
    elif gen_tokens == 0 and nt > 0:
        # NO generation logged = output completed before first timing check at ~100 tokens
        # This is the EVALUATOR pattern: large prompt + very short output
        if nt <= 400:
            # Small prompt, no gen = could be classifier with fast gen
            CLASSIFIER += 1
        else:
            EVALUATOR += 1  # Large prompt, no gen = evaluator
    elif gen_tokens > 0 and gen_tokens < 80 and nt > 400:
        # Generated < 80 tokens with large prompt = evaluator (VERDICT text)
        EVALUATOR += 1
    elif gen_tokens > 0 and gen_tokens < 80 and nt <= 400:
        # Generated < 80 tokens with small prompt = compressor
        COMPRESSOR += 1
    elif gen_tokens >= 80 and nt > 400:
        # Generated 80+ tokens with large prompt = solver (generating code)
        SOLVER += 1
    elif gen_tokens >= 80:
        # Generated 80+ tokens but small total = weird
        SOLVER += 1
    else:
        UNKNOWN += 1

print("=" * 60)
print("CLASSIFICATION BY GENERATION SIZE")
print("=" * 60)
print(f"  CLASSIFIER/SAFETY: {CLASSIFIER}")
print(f"  EVALUATOR:         {EVALUATOR}")
print(f"  COMPRESSOR:        {COMPRESSOR}")
print(f"  SOLVER:            {SOLVER}")
print(f"  UNKNOWN:           {UNKNOWN}")
print(f"  TOTAL:             {len(tasks)}")

# Per-step: group sequence into steps using evaluator as step boundaries
print("\n" + "=" * 60)
print("SEQUENCE WITH CORRECT CLASSIFICATION")
print("=" * 60)

steps = []
current_step = {'label': 'preamble', 'solvers': 0, 'evals': 0, 'comps': 0, 'classifiers': 0}
steps.append(current_step)
step_idx = 0

for tid, t in sorted(tasks.items(), key=lambda x: x[0]):
    nt = t['release_tokens']
    nd = t['n_decoded_max']
    gl = t['gen_logs']
    gen_tokens = nd if nd > 0 else 0
    
    if nt == 0:
        cat = "NODATA"
        continue
    elif nt <= 100:
        cat = "CLS"
    elif gen_tokens == 0 and nt > 400:
        cat = "EVAL"
    elif gen_tokens > 0 and gen_tokens < 80:
        cat = "COMP"
    elif gen_tokens >= 80:
        cat = "SOLVE"
    else:
        cat = f"?({nt}t,{gen_tokens}g)"
    
    if cat in ('CLS',):
        current_step['classifiers'] += 1
    elif cat == 'EVAL':
        current_step['evals'] += 1
    elif cat == 'COMP':
        # Compressor marks step end
        current_step['comps'] += 1
        step_idx += 1
        current_step = {'label': f'step_{step_idx}', 'solvers': 0, 'evals': 0, 'comps': 0, 'classifiers': 0}
        steps.append(current_step)
    elif cat == 'SOLVE':
        current_step['solvers'] += 1

print("\nPER-STEP BREAKDOWN:")
for i, s in enumerate(steps):
    total = s['solvers'] + s['evals'] + s['comps'] + s['classifiers']
    if total == 0:
        continue
    retries = max(0, s['solvers'] - 1)
    flag = "❌ >3" if s['solvers'] > 3 else "✅"
    print(f"  {s['label']:20s}: {s['solvers']:2d} solve, {s['evals']:2d} eval, {s['comps']:2d} comp, {s['classifiers']:2d} cls — {retries:2d} retries {flag}")

# Print the full sequence for debugging
print("\n" + "=" * 60)
print("FULL SEQUENCE (first 40 tasks)")
print("=" * 60)
for tid, t in list(sorted(tasks.items(), key=lambda x: x[0]))[:40]:
    nt = t['release_tokens']
    nd = t['n_decoded_max']
    gl = t['gen_logs']
    gen_tokens = nd if nd > 0 else 0
    
    if nt == 0:
        cat = "NODATA"
    elif nt <= 100:
        cat = "CLS"
    elif gen_tokens == 0 and nt > 400:
        cat = "EVAL"
    elif gen_tokens > 0 and gen_tokens < 80:
        cat = "COMP"
    elif gen_tokens >= 80:
        cat = "SOLVE"
    else:
        cat = f"?({nt}t,{gen_tokens}g)"
    
    print(f"  {tid:5d} | {nt:5d}t | {gen_tokens:4d}g | {gl:2d}logs | {cat}")
