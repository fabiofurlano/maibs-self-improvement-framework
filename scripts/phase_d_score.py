#!/usr/bin/env python3.10
"""Score Phase D outputs against the 6 criteria. Uses Gemma as evaluator for Run 1 logs,
manual/automated checks for Run 2 bare output."""

import sys, os, json, re

sys.path.insert(0, '/tmp/maibs-self-improvement-framework')
from maibs_mcp_server import call_gemma

EVALUATOR_SYSTEM = """You are an output evaluator. You receive a task's ORIGINAL criteria and a proposed solution.
Check the solution against EVERY criterion. Reply in exactly this format:

VERDICT: PASS
or
VERDICT: REJECT
REASON: <one sentence, the SPECIFIC criterion that failed and how>

Do not suggest fixes. Do not rewrite the solution. Judge only."""

CRITERIA = [
    "Uses requests library correctly",
    "Uses BeautifulSoup to parse HTML",
    "Filters external links only (not internal)",
    "Writes to CSV correctly",
    "Error handling for bad URLs present",
    "README exists and is accurate",
]

def score_output(label, output_text, criteria):
    """Score an output against the 6 criteria using Gemma evaluator."""
    results = {}
    for i, criterion in enumerate(criteria):
        prompt = f"""ORIGINAL CRITERION:
{criterion}

SOLUTION TO EVALUATE:
{output_text[:4000]}

Check if the solution satisfies this criterion. Reply with VERDICT: PASS or VERDICT: REJECT, then REASON: ..."""
        try:
            full_prompt = f"{EVALUATOR_SYSTEM}\n\nORIGINAL CRITERION:\n{criterion}\n\nSOLUTION TO EVALUATE:\n{output_text[:4000]}\n\nCheck if the solution satisfies this criterion."
            response, elapsed = call_gemma(full_prompt, timeout=120)
            verdict = "PASS" if "VERDICT: PASS" in response else "REJECT" if "VERDICT: REJECT" in response else "UNCLEAR"
            reason_match = re.search(r'REASON:\s*(.+?)(?:\n|$)', response)
            reason = reason_match.group(1).strip() if reason_match else response[:200]
            results[f"c{i+1}"] = {"criterion": criterion, "verdict": verdict, "reason": reason, "elapsed": elapsed}
        except Exception as e:
            results[f"c{i+1}"] = {"criterion": criterion, "verdict": "ERROR", "reason": str(e)}
    return results

if __name__ == "__main__":
    raw_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/maibs-self-improvement-framework/projects/maibs/phase-d-raw.json"
    with open(raw_path) as f:
        data = json.load(f)
    
    # Score Run 1
    r1 = data["run1_gemma_pipeline"]["result"]
    r1_output = ""
    if "steps" in r1:
        for s in r1.get("steps", []):
            if "output" in s:
                r1_output += f"\n--- Step output ---\n{s['output'][:500]}"
    elif "solution" in r1:
        r1_output = r1["solution"]
    r1_output = r1_output or json.dumps(r1, default=str)[:4000]
    
    print("Scoring Run 1 (Gemma + pipeline)...")
    r1_scores = score_output("Run 1", r1_output, CRITERIA)
    
    # Score Run 2
    r2 = data["run2_frontier_bare"]["result"]
    r2_output = r2.get("raw_output", json.dumps(r2, default=str))[:4000]
    
    print("Scoring Run 2 (Frontier bare)...")
    r2_scores = score_output("Run 2", r2_output, CRITERIA)
    
    # Build scoreboard
    scoreboard = {
        "run1_gemma_pipeline": r1_scores,
        "run2_frontier_bare": r2_scores,
    }
    
    score_path = "/tmp/maibs-self-improvement-framework/projects/maibs/phase-d-scores.json"
    with open(score_path, "w") as f:
        json.dump(scoreboard, f, indent=2)
    
    # Print summary
    r1_total = sum(1 for c in r1_scores.values() if c["verdict"] == "PASS")
    r2_total = sum(1 for c in r2_scores.values() if c["verdict"] == "PASS")
    
    print(f"\n{'='*60}")
    print(f"SCOREBOARD")
    print(f"{'='*60}")
    print(f"{'Criterion':<45} {'Run1':<8} {'Run2':<8}")
    print(f"{'-'*60}")
    for i, c in enumerate(CRITERIA):
        r1v = r1_scores.get(f"c{i+1}", {}).get("verdict", "?")
        r2v = r2_scores.get(f"c{i+1}", {}).get("verdict", "?")
        print(f"{c:<45} {r1v:<8} {r2v:<8}")
    print(f"{'-'*60}")
    print(f"{'TOTAL':<45} {r1_total}/6{'':>3} {r2_total}/6")
    
    print(f"\nScores saved to {score_path}")
