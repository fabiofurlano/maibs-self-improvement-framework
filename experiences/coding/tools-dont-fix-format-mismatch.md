# Pattern: Tools Don't Fix Format Mismatches

**Discovery date:** 2026-06-10
**Source:** Proof run B3 — zero flips vs B2 (both 45%)

## The Finding

Adding web search and library documentation (Context7) to the prompt did NOT improve pass rate beyond B2 (reasoning lifeline alone). The bottleneck is not algorithm knowledge — it's task-specific format matching.

## Evidence

11 tasks failed in B2. All 11 still fail in B3 with tools available:
- 9 AssertionErrors: correct algorithm, wrong output format
- 2 TypeErrors: wrong parameter count

## Why Tools Don't Help Here

MBPP tasks are self-contained — they don't require external library knowledge. The model already knows the algorithms. What it doesn't know is:
- The exact function name expected by the test assertions
- The precise output format (tuple vs list, return type)

Web search returns general Python examples. Context7 returns library API docs. Neither contains the task-specific format requirements embedded in the test assertions.

## When Tools WOULD Help

Tools become valuable when:
1. The task requires a library the model doesn't know (e.g., a specific numpy function signature)
2. The algorithm is novel and the model needs reference implementations
3. The task involves current events or version-specific behavior

For benchmark tasks with deterministic test assertions, the ceiling is determined by format visibility, not information access.

## Actionable Rule

**Don't add tools to fix format mismatches. Add tools for algorithm discovery.** For benchmark tasks, invest in extracting function signatures and I/O formats from test code — that's the information that closed the 0%→80% gap.
