#!/usr/bin/env python3.10
"""Score both Run 1 and Run 2 against the 6 Phase D criteria."""

import sys, os, json, re, time
sys.path.insert(0, '/tmp/maibs-self-improvement-framework')
from maibs_mcp_server import call_gemma, EVALUATOR_SYSTEM

CRITERIA = [
    "Uses requests library correctly",
    "Uses BeautifulSoup to parse HTML",
    "Filters external links only (not internal)",
    "Writes to CSV correctly",
    "Error handling for bad URLs present",
    "README exists and is accurate",
]

def score_criteria(output_text, label):
    results = {}
    for i, c in enumerate(CRITERIA):
        prompt = f"{EVALUATOR_SYSTEM}\n\nORIGINAL CRITERION:\n{c}\n\nSOLUTION TO EVALUATE:\n{output_text[:3000]}\n\nCheck if the solution satisfies this criterion."
        out, elapsed = call_gemma(prompt, timeout=120)
        verdict = "PASS" if "VERDICT: PASS" in out else "REJECT" if "VERDICT: REJECT" in out else "UNCLEAR"
        m = re.search(r'REASON:\s*(.+?)(?:\n|$)', out)
        reason = m.group(1).strip() if m else out[:150]
        results[f"c{i+1}"] = {"criterion": c, "verdict": verdict, "reason": reason}
        print(f"  [{label}] c{i+1}: {verdict} ({elapsed:.1f}s) — {reason[:100]}", flush=True)
    return results

# Load Run 1 solution assembly
with open('projects/maibs/phase-d-run1-raw.json') as f:
    r1 = json.load(f)
# Concatenate solutions from passed steps
r1_parts = []
for s in r1.get('steps', []):
    if s.get('solution'):
        r1_parts.append(f"// Step: {s.get('goal','')[:60]}\n{s['solution'][:500]}")
r1_output = '\n\n'.join(r1_parts)[:4000] or "(no solutions produced)"

# Load Run 2 output
with open('projects/maibs/phase-d-run2-raw.json') as f:
    r2 = json.load(f)
r2_output = r2['raw_output'][:4000]

print("Scoring Run 1 (Gemma + pipeline)...", flush=True)
r1_scores = score_criteria(r1_output, "R1")

print("\nScoring Run 2 (DeepSeek bare)...", flush=True)
r2_scores = score_criteria(r2_output, "R2")

# Build scoreboard
r1_total = sum(1 for v in r1_scores.values() if v['verdict'] == 'PASS')
r2_total = sum(1 for v in r2_scores.values() if v['verdict'] == 'PASS')

scoreboard = {
    "run1_gemma_pipeline": {"scores": r1_scores, "total": f"{r1_total}/6"},
    "run2_frontier_bare": {"scores": r2_scores, "total": f"{r2_total}/6"},
}

with open('projects/maibs/phase-d-scores.json', 'w') as f:
    json.dump(scoreboard, f, indent=2)

print(f"\n{'='*60}")
print(f"FINAL SCOREBOARD")
print(f"{'='*60}")
print(f"{'Criterion':<45} {'Run1':<8} {'Run2':<8}")
print(f"{'-'*60}")
for i, c in enumerate(CRITERIA):
    r1v = r1_scores[f"c{i+1}"]["verdict"]
    r2v = r2_scores[f"c{i+1}"]["verdict"]
    print(f"{c:<45} {r1v:<8} {r2v:<8}")
print(f"{'-'*60}")
print(f"{'TOTAL':<45} {r1_total}/6{'':>3} {r2_total}/6")

print(f"\n=== RUN 1 PER-CRITERION DETAILS ===")
for k, v in r1_scores.items():
    print(f"  {k} {v['verdict']}: {v['reason'][:120]}")

print(f"\n=== RUN 2 PER-CRITERION DETAILS ===")
for k, v in r2_scores.items():
    print(f"  {k} {v['verdict']}: {v['reason'][:120]}")
