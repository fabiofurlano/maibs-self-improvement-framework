# Pattern: AssertionError needs richer context than bare error message

**Discovery date:** 2026-06-10
**Source:** Proof run condition B, 6 AssertionError tasks — zero flipped

## The Pattern

When M3 produces syntactically valid code that passes the wrong output, the oracle reports a bare AssertionError with no traceback detail. The model cannot infer:

- Which assertion failed
- What the expected output was
- What the actual output was
- Whether it's an off-by-one, wrong type, wrong edge case handling

## Why Memory Alone Doesn't Help

Condition B injected: `"Error: AssertionError"` — that's it. No actionable information.

Compare to NameErrors: `"Error: name 'even_binomial_Coeff_Sum' is not defined"` — this IS the fix instruction.

## What Would Help

- Show the failing test assertion with expected vs actual values
- Show a passing example for a similar task
- DeepSeek reasoning lifeline (Phase 2) with full problem analysis

## Evidence

6/20 tasks in B failed with AssertionError. Zero flipped. Even with test assertions shown (condition C), 4/20 still failed — these are M3's algorithmic ceiling.
