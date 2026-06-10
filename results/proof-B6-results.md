# Proof B6 — Experience Recall Injection (Falsified)

**Date:** 2026-06-11
**Model:** Gemma 4 E4B (QAT-UD-Q4_K_XL, local llama-server)
**Test set:** 20 fixed MBPP tasks (same set as B1–B4-local)
**Hypothesis:** Injecting Jaccard-matched past solutions from a 58-task memory pool would help Gemma solve the 5 tasks that B4-local leaves stuck.
**Result:** **40% (8/20). B4-control in the same run: 50% (10/20). −10pp regression. Hypothesis falsified.**

---

## 1. Setup

- **Memory pool:** 58 MBPP solutions, 0 overlap with the 20 test tasks (Jaccard>0.5 anti-cheat verified at seed time).
- **Recall mechanism:** for each test task, Jaccard token overlap (threshold ≥ 3) against the 58-task pool. Top match loaded. The full detail file (worked Python solution) was injected into the prompt, prefixed "PAST EXPERIENCE:".
- **Solver:** Gemma 4 E4B local, temperature=0, 2 attempts.
- **Baseline (same run):** B4-control = format hint only, no recall. Same 20 tasks, same Gemma state.
- **Model was NOT fine-tuned.** This is a pure prompt-level intervention.

Full match log: `results/proof-B6-match-log.txt`. Per-task results: `results/proof-B6.json`.

---

## 2. Result

| Condition | Pass | Rate | Δ vs B4-local baseline (60%) |
|-----------|------|------|------------------------------|
| B4-local (prior run) | 12/20 | 60% | — |
| **B4-control (same run as B6)** | **10/20** | **50%** | −10pp run-to-run noise |
| **B6-recall (same run)** | **8/20** | **40%** | **−20pp vs B4-local, −10pp vs same-run control** |

- 2 flips (B6 turned a B4-fail into a B6-pass): MBPP/448 (perrin numbers), MBPP/380 (2D array).
- 4 regressions (B6 broke a task that B4 passed in the same run): MBPP/393, MBPP/411, MBPP/211, MBPP/144. All four went from clean `attempt_1_pass` to `SyntaxError: unterminated triple-quoted string literal` after recall was added.

This is the **second time** injecting extra context into Gemma's prompt has hurt it. B3b (Context7 docs before attempt) dropped M3 from 45% to 35% on the same task family. The pattern: **a 4B model treats injected context as additional prompt content to continue, not as reference material to consult.**

---

## 3. Diagnosis: two distinct failure modes, both real

### Mode A — Matches are wrong (hypothesis 1 confirmed)

The Jaccard token-overlap matcher is lexical, not semantic. Of 20 matches:

- **2 were semantically correct:** MBPP/448 (perrin numbers) → MBPP/133 (sum of negative numbers) — same arithmetic pattern, correct algorithm. **MBPP/380** → MBPP/241 (3D array) — correct algorithm template. These are the 2 flips.
- **3 were wrong but superficially similar:** MBPP/22 (first duplicate) → MBPP/145 (max difference) — both list problems, totally different algorithm. MBPP/473 (tuple intersection) → MBPP/63 (max difference in array) — share "list" and "find" tokens, no useful algorithmic overlap. MBPP/111 (common in nested lists) → MBPP/40 (frequency of elements) — only superficially related.
- **15 were irrelevant or actively misleading:** Examples include MBPP/264 (dog's age, a domain-math task) → MBPP/133 (sum of negatives), and MBPP/459 (remove uppercase substrings, regex) → MBPP/377 (remove character occurrences, string manipulation but different problem).

The Jaccard threshold of 3 was too low. But raising it doesn't fix Mode B.

### Mode B — Recall injects noise that Gemma continues as code (hypothesis 2 confirmed)

The four regressions (MBPP/393, 411, 211, 144) all have the same shape: B4-control got a clean first-attempt pass with just the format hint. B6 added a `PAST EXPERIENCE:` block with a worked solution. Gemma's output then becomes a `SyntaxError: unterminated triple-quoted string literal (detected at line 23/32/etc)`.

The worked solutions in the pool were 25–40 lines of Python. When injected as prompt context, Gemma appears to start **regurgitating the example as part of its own answer**, breaking out of the `def func_name():` scaffold into a multi-section response with explanatory text. The format-hint said "Return ONLY the function code in a single markdown code block" but the example's length and structure pulled the model into explanatory mode.

This is the same failure shape as B3b (M3 + Context7 docs). In both cases, a small model with limited instruction-following headroom treats injected text as content to extend, not as reference.

---

## 4. The 5 stuck tasks: did recall help?

These are the tasks B4-local never solved. The Phase 6 hypothesis was that recall would crack them.

| Task | B4-local (12/20) | B4-control (same run) | B6-recall (same run) | Flipped? |
|------|------------------|------------------------|------------------------|----------|
| MBPP/22 (first duplicate) | ❌ | ❌ | ❌ | No |
| MBPP/264 (dog's age) | ❌ | ❌ | ❌ | No (no useful match in pool — match to MBPP/133 was wrong) |
| MBPP/268 (n'th star number) | ❌ | ❌ | ❌ | No |
| MBPP/448 (perrin sum) | ❌ | ❌ | ✅ | **YES** |
| MBPP/473 (tuple intersection) | ❌ | ❌ | ❌ | No |

**1 of 5 flipped.** Not enough to justify the 4 regressions and the −10pp overall regression.

---

## 5. What this rules out

- ❌ "Add past solutions to the prompt" — doesn't help, actively hurts.
- ❌ "Use Jaccard lexical recall" — too noisy, the matches are mostly wrong.
- ❌ "Inject semantic-similar past solutions" — same Mode B failure (the format problem isn't about match quality, it's about Gemma's inability to ignore injected content).
- ❌ "Inject summaries instead of full solutions" — same Mode B (any extra text burns instruction-following budget on a 4B model).
- ❌ "Confidence-gate recall" — same Mode B (the failure isn't about which past solution to inject, it's about Gemma treating *any* injected code as content to extend).
- ❌ "Add a different retrieval backend" (Tavily, semantic embeddings, etc.) — **not applicable to MBPP**. The benchmark is closed-book; there is no external knowledge to retrieve. Any retrieval is necessarily from the same pool, which means Mode B reproduces.
- ❌ **Tavily-for-MBPP is parked for Phase 11 (real-world tasks).** It is not a candidate for this experiment.

The injection family has now failed twice (B3b, B6). It is closed.

---

## 6. What remains open

- **Better prompting of the same model** — Phase 7a. Add explicit "reason step by step" instructions on the existing format hint. No new context. If this doesn't move the number, the conclusion is clear: the path to 80% is fine-tuning (Phase 8), not prompting.
- **Fine-tuning Gemma on worked MBPP solutions** — Phase 8. The 58-task pool + 3 original solves is already a small but real training set. LoRA on a 4B base is cheap on CPU.
- **Switching to a different local model** — parked. The model decision is downstream of the prompting-vs-fine-tuning decision.

---

## 7. Numbers to memorize

- **Phase 6 ceiling: 40%.** This is the worst we've seen on this 20-task set since the bare-baseline condition. Recall injection is a regression, not a neutral.
- **B4-control is not perfectly stable run-to-run** — 60% in B4-local, 50% in this run, on the same 20 tasks. Treat the 10pp gap between B4-control and B6-recall as suggestive, not decisive, but the direction is unambiguous.
- **1 flip per 4 regressions** is not a trade anyone would take.
