# Pattern: NameError → PASS with function name injection

**Discovery date:** 2026-06-10
**Source:** Proof run condition B, 3 flips from baseline 0%

## The Pattern

When MiniMax M3 solves MBPP tasks, it invents function names (e.g., `sum_even_index_binomial`).
The test assertions call a specific name (e.g., `even_binomial_Coeff_Sum`).
Result: NameError on every first attempt.

## The Fix

Inject the correct function name into the prompt. The test assertions contain it:

```python
# Test assertion reveals the function name:
assert even_binomial_Coeff_Sum(4) == 8

# Before (A, no memory): model invents "sum_even_index_binomial" → NameError
# After  (B, with memory): model sees NameError, writes "even_binomial_Coeff_Sum" → PASS
```

## Evidence

MBPP/274 flipped from FAIL (NameError) to PASS when failure memory showed:
- Error: `name 'even_binomial_Coeff_Sum' is not defined`
- Fix: renamed function to `even_binomial_Coeff_Sum`

Identical logic. Only the function name changed.

## Actionable Rule

**Before solving any MBPP task, extract the function name from test assertions and include it in the prompt.** This alone closes the gap between 0% and 15% baseline.
