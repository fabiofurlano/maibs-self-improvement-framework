# Pattern: Reasoning Lifeline — Expert Model Analysis Fixes Double-Failures

**Discovery date:** 2026-06-10
**Source:** Proof run B2, 6 new flips beyond condition B (15% → 45%)

## The Pattern

When MiniMax M3 fails a task twice (A=FAIL, B=FAIL):
1. Call DeepSeek V4 Pro with the problem + both failed attempts
2. DeepSeek analyzes WHY each attempt failed
3. DeepSeek explains the correct approach
4. Inject DeepSeek's reasoning into M3's third attempt
5. M3 solves correctly

## Why It Works

Failure memory (B) only tells M3 *what* went wrong. DeepSeek reasoning (B2) tells M3 *why* it went wrong and *how* to fix it.

```
B (failure memory):  "Error: NameError — name 'cal_sum' is not defined"
                      → Model knows it got the name wrong, but doesn't know the RIGHT name

B2 (DeepSeek reasoning): "This problem requires a function that... The test assertions show
                          the expected function name is 'cal_sum' which takes these parameters..."
                      → Model understands the full context and writes the correct solution
```

## Evidence

6 tasks flipped B→B2:
- 4 NameErrors that failure memory alone couldn't fix
- 1 AssertionError (DeepSeek explained the edge case)
- 1 TypeError (DeepSeek explained the correct parameter signature)

11 tasks still fail: 9 AssertionErrors + 2 wrong output format — these are M3's raw algorithmic ceiling.

## Actionable Rule

**When a task fails twice, call a stronger model for analysis.** One API call tripled the improvement rate. The 10:1 cost ratio (17 DeepSeek calls for 6 new passes) is worth it — each DeepSeek call is cheap compared to the value of a corrected solution.
