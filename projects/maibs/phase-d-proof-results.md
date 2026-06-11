# Phase D — The Proof Test Results

> **Ran:** 2026-06-11 | **Model:** Gemma 4 E4B (CPU) vs DeepSeek V3 (cloud bare)

## Claim Being Tested

> "A free 4B model with engineered context and per-step evaluation completes long tasks more reliably than a frontier model with raw accumulating context."

## Task

"Build a working web scraper: fetch a public webpage using requests, extract all hyperlinks using BeautifulSoup, filter to external links only, write results to a CSV file, include error handling for bad URLs, write a usage README."

---

## Run 1 — Gemma E4B + Full Pipeline

**Duration:** 71.4 minutes | **Steps:** 10 (8 passed, 2 failed) | **Context:** max 948 chars (≤4K ✅)

### Step-by-step results

| Step | Status | Time | Iters | Oracle | Evaluator | Lifeline |
|------|--------|------|-------|--------|-----------|----------|
| 1. Scaffold project | ✅ PASS | 549s | 3 | — | REJECT×3 (empty) | ✅ rescued |
| 2. fetch_page() | ✅ PASS | 468s | 3 | SyntaxError×3 | — | ✅ rescued |
| 3. extract_links() | ❌ FAIL | 428s | 3 | SyntaxError×3 | REJECT (empty) | ❌ failed |
| 4. classify_links() | ✅ PASS | 137s | 1 | — | PASS | — |
| 5. write_csv() | ✅ PASS | 298s | 2 | SyntaxError | PASS | — |
| 6. CLI with argparse | ✅ PASS | 492s | 3 | SyntaxError×2 | REJECT×1 | ✅ rescued |
| 7. Error handling | ❌ FAIL | 513s | 3 | SyntaxError×2 | REJECT×2 (empty) | ❌ failed |
| 8. Edge cases | ✅ PASS | 516s | 3 | SyntaxError×2 | REJECT×1 (empty) | ✅ rescued |
| 9. README | ✅ PASS | — | 3 | SyntaxError×3 | — | ✅ rescued |
| 10. Integration test | ✅ PASS | — | 2 | SyntaxError | PASS | — |

### Key findings

- **Gemma produces broken syntax in ~70% of code generations** on CPU. Most common errors: unterminated string literals, missing except/finally blocks, unclosed brackets.
- **Reasoning lifeline rescued 6/10 steps** but failed for 2 (extract_links, error handling).
- **Step 4 was the only clean first-attempt pass** — the simplest task (dictionary classification).
- **Assembled output is fragmented**: individual step solutions don't compose into a working scraper. The context compression between steps (21% floor) lost critical coherence — each step generated code in isolation, not building on previous steps.
- **Context stayed well under 4K** (max 948 chars) — the compression floor worked mechanically but left steps with insufficient context to integrate with prior work.

---

## Run 2 — DeepSeek V4 Pro, Single Prompt, No Tools

**Duration:** 37 seconds | **Tokens:** 1507 (211 prompt + 1296 completion) | **Output:** 5584 chars

### Output produced

- `scraper.py` — 130-line WebScraper class: fetch_page(), extract_links(), _is_external(), write_to_csv(), main(), CLI via sys.argv
- `README.md` — installation, usage example, output format, error handling, limitations

### 6-Criteria Scorecard

| # | Criterion | Run 1 | Run 2 | Notes |
|---|-----------|-------|-------|-------|
| 1 | Uses `requests` correctly | ❌ | ✅ | Run 1: step solutions fragmented, fetch_page incomplete |
| 2 | Uses BeautifulSoup | ❌ | ✅ | Run 1: extract_links step FAILED entirely |
| 3 | Filters external links only | ❌ | ✅ | Run 1: classify_links exists but not wired to extract |
| 4 | Writes to CSV correctly | ❌ | ✅ | Run 1: write_csv truncated, missing closing paren |
| 5 | Error handling for bad URLs | ❌ | ✅ | Run 1: error handling step FAILED |
| 6 | README exists + accurate | ❌ | ✅ | Run 1: README step passed but wrote over MAIBS README |

| | **Run 1** | **Run 2** |
|---|---|---|
| **TOTAL** | **0/6** | **6/6** |

---

## Verdict

**The thesis claim is REJECTED.**

The pipeline completed 80% of individual steps, but the output does not compose into a working product. Three root causes identified:

1. **Context compression destroyed assembly coherence.** Each step started fresh with ≤948 chars of context. Steps couldn't build on prior work because the compression stripped variable names, file paths, and integration points.

2. **Gemma's code generation quality on CPU is too low.** 70%+ of generated code had syntax errors. The 3-iteration retry + lifeline loop rescued most failures but couldn't compensate for the fundamental quality gap.

3. **Per-step evaluation ≠ product evaluation.** The evaluator checked individual step criteria but had no visibility into cross-step integration. Steps passed in isolation but failed to compose.

### What survived

- **Phase C infrastructure works**: classify, safety gate, planning, oracle, evaluator, compression, lifeline — all wired end-to-end
- **Step 4 proved the best case**: clean first-attempt pass when the task was simple and self-contained
- **Context ≤4K cap held** at every step — the mechanical constraint was satisfied

### Frontier model drift

DeepSeek V4 Pro did NOT drift on this task. All 6 criteria satisfied in one shot. The task was within its single-prompt capabilities. For this task length (5-7 steps), a frontier model's context window easily handled the full specification without degradation.

---

## What This Means for MAIBS

The pipeline's value proposition shifts:

- **Short tasks (1-2 steps):** Gemma alone is insufficient (0% on MBPP). Format hints bring it to 60-80%. The pipeline's overhead isn't justified for single-step tasks.
- **Medium tasks (3-7 steps):** Frontier models handle these natively. The pipeline adds cost without benefit.
- **Long tasks (15+ steps):** This is where context rot might give Gemma+pipeline an edge — but the pipeline's own context compression prevents it from reaching that length. A chicken-and-egg problem.

**Recommendation:** Phase D result is conclusive. Do not pursue longer-task variants. The pipeline's core assumption — that per-step context cleaning preserves coherence — is falsified. The compression that prevents rot also prevents integration.

---

## Raw Data

- Run 1 raw: `projects/maibs/phase-d-run1-raw.json`
- Run 2 raw: `projects/maibs/phase-d-run2-raw.json`
- Test log: `/tmp/phase-d-run1-manual.log`
