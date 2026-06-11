#!/usr/bin/env python3.10
"""Phase A gate test — Evaluator node.

Tests evaluate_output() against 5 tasks:
  4 with planted criteria violations → expect REJECT
  1 fully compliant → expect PASS

Target: ≥4/5 planted violations caught, ZERO false rejections.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from maibs_mcp_server import evaluate_output

# ── Test cases ──────────────────────────────────────
# Each: (label, task_description, original_criteria, solution, has_violation)

TESTS = [
    # ──── VIOLATION 1: must use recursion, solution uses while loop ────
    (
        "T1: factorial (recursion required)",
        "Write a function factorial(n) that returns n!",
        "Must use recursion (no loops). The function must call itself.",
        """def factorial(n):
    result = 1
    i = 1
    while i <= n:
        result *= i
        i += 1
    return result""",
        True,
    ),
    # ──── VIOLATION 2: must use re module, solution uses string methods ────
    (
        "T2: extract emails (regex required)",
        "Write a function extract_emails(text) that returns all email addresses",
        "Must use the re module (regular expressions). Do not use string methods alone.",
        """def extract_emails(text):
    words = text.split()
    emails = []
    for w in words:
        if '@' in w and '.' in w.split('@')[-1]:
            emails.append(w)
    return emails""",
        True,
    ),
    # ──── VIOLATION 3: must return dict, solution returns list of tuples ────
    (
        "T3: word count (must return dict)",
        "Write a function word_count(text) that counts word frequency",
        "Must return a dict (dictionary). Keys are words, values are counts.",
        """def word_count(text):
    words = text.lower().split()
    result = []
    for w in set(words):
        result.append((w, words.count(w)))
    return result""",
        True,
    ),
    # ──── VIOLATION 4: must use list comprehension, solution uses for loop ────
    (
        "T4: square evens (comprehension required)",
        "Write a function square_evens(lst) that returns squares of even numbers",
        "Must use a list comprehension for the final output. A single list comprehension must produce the result.",
        """def square_evens(lst):
    result = []
    for x in lst:
        if x % 2 == 0:
            result.append(x * x)
    return result""",
        True,
    ),
    # ──── COMPLIANT: solution actually meets all criteria ────
    (
        "T5: merge sorted lists (compliant)",
        "Write a function merge_sorted(a, b) that merges two sorted lists",
        "Must return a list (not a generator or iterator). Must use the built-in sorted() function.",
        """def merge_sorted(a, b):
    combined = a + b
    return sorted(combined)""",
        False,
    ),
]

# ── Run ─────────────────────────────────────────────
print("=" * 68)
print("  PHASE A GATE TEST — Evaluator Node")
print("  Target: catch ≥4/5 planted violations, 0 false rejections")
print("=" * 68)
print()

results = []
violations_caught = 0
violations_total = 0
false_rejections = 0
false_passes = 0  # violation planted but not caught

for label, task, criteria, solution, has_violation in TESTS:
    print(f"--- {label} ---")
    print(f"  Criteria: {criteria[:80]}...")
    print(f"  Violation planted: {'YES' if has_violation else 'NO (compliant)'}")
    
    t0 = time.time()
    passed, reason = evaluate_output(solution, criteria)
    elapsed = time.time() - t0
    
    verdict = "PASS" if passed else "REJECT"
    expected_verdict = "REJECT" if has_violation else "PASS"
    correct = verdict == expected_verdict
    
    if has_violation:
        violations_total += 1
        if verdict == "REJECT":
            violations_caught += 1
            status = "✓ CAUGHT"
        else:
            false_passes += 1
            status = "✗ MISSED (false pass)"
    else:
        if verdict == "REJECT":
            false_rejections += 1
            status = "✗ FALSE REJECTION"
        else:
            status = "✓ CORRECT PASS"
    
    print(f"  Verdict: {verdict} | Reason: {reason[:100]}")
    print(f"  Time: {elapsed:.1f}s | {status}")
    print()
    
    results.append({
        "task": label,
        "violation_planted": has_violation,
        "expected": expected_verdict,
        "actual": verdict,
        "reason": reason[:150],
        "correct": correct,
        "time_s": round(elapsed, 1),
    })

# ── Summary table ───────────────────────────────────
print("=" * 68)
print("  GATE RESULTS")
print("=" * 68)
print(f"  {'Task':<35} {'Planted':^8} {'Expected':^8} {'Actual':^8} {'OK?':^5}")
print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*5}")
for r in results:
    ok = "✓" if r["correct"] else "✗"
    print(f"  {r['task']:<35} {'YES' if r['violation_planted'] else 'NO':^8} {r['expected']:^8} {r['actual']:^8} {ok:^5}")
print()
print(f"  Violations caught:  {violations_caught}/{violations_total}")
print(f"  False rejections:   {false_rejections}")
print(f"  False passes:       {false_passes}")
print()

# ── Gate decision ───────────────────────────────────
gate_passed = violations_caught >= 4 and false_rejections == 0
print(f"  GATE: {'✅ PASS' if gate_passed else '❌ FAIL'}")
if gate_passed:
    print(f"  Phase B is unblocked.")
    print(f"  Evaluator meets spec: caught ≥4/5 violations ({violations_caught}/{violations_total})")
    print(f"  Zero false rejections on compliant solutions.")
else:
    if violations_caught < 4:
        print(f"  FAIL: Only {violations_caught}/5 violations caught (need ≥4)")
    if false_rejections > 0:
        print(f"  FAIL: {false_rejections} false rejection(s) on compliant solution")
print()

# ── Return code for scripting ───────────────────────
sys.exit(0 if gate_passed else 1)
