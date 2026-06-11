# MAIBS — What This Is

> **New here?** → [QUICKSTART.md](QUICKSTART.md) — get a result in 5 minutes. No Hermes CLI needed. Just a free OpenRouter key.

A small local AI model — the kind that runs free on a laptop — that gets measurably better at coding tasks the more it works. Not by retraining. Not by switching to a bigger model. By remembering its own mistakes and learning how to frame problems correctly before it starts.

The result after 7 experiments on 20 real coding tasks:

| What the system knew | Pass rate |
|---|---|
| Nothing | 0% |
| Its own past failures | 15% |
| Past failures + expert reasoning on demand | 45% |
| Past failures + how to frame the problem | 80% |

The expensive API call got us to 45%. The free format hint got us to 80%. Knowing how to talk to the model beat throwing money at it. That's the whole point of this project.

## ⚠️ Vibe Coder Alert

This repo was built by one person, no team, no lab, no budget, running on a ThinkPad in Italy. It probably has bugs. Some things might not work on your machine. I'm not the sharpest tool in the toolbox — it's likely a fluke that any of this works at all. You've been warned. PRs welcome.

## 🖥 Dashboard

Open `dashboard/index.html` in a browser. Configure backends, toggle pipeline layers, type a task, and hit Run. The dashboard calls the live MCP server (`solve_with_memory` on port 8282) and shows pipeline stages in real time.

[→ Dashboard README](dashboard/README-dashboard.md)

---

## What MAIBS Actually Is

**Memory-Augmented In-Context Bootstrapping System.** A self-hostable framework where an LLM learns from its own experience. Given a coding task:

1. **Solve** — the model attempts the problem
2. **Oracle** — runs the code against test assertions → PASS or FAIL
3. **Memory-Write** — persists the verdict + error + solution to an experience database
4. **Memory-Read** — next time a similar task appears, injects past successes and failures as context

The pipeline is an [Archon](https://github.com/coleam00/archon) 5-node DAG. The experience database is SQLite. The solver can be any model — we tested with MiniMax M3 (API) and are integrating Google's Gemma 4 E4B running locally on the ThinkPad (QAT-compressed, 4GB, 6.5 tok/s on CPU).

## Architecture

```
Task → [experience DB] → [format hints] → [solve] → [oracle] → [write verdict]
                            ↑                          ↑
                      (function name +          [reasoning lifeline]
                       example extracted        (DeepSeek V4 Pro —
                       from test assertions)     only when needed)
```

The key insight: **most of the gap between a small model and ceiling performance isn't about reasoning power — it's about knowing how to frame the problem.** Extract the function name and one example from the task spec, inject it before the first attempt, and a 4B-parameter model hits 80% — matching the oracle cheat ceiling where the model sees the actual test assertions.

## The 7 Experiments — Full Table

Same 20 MBPP coding tasks, MiniMax M3 as solver. Each condition adds more context before the first attempt:

| Condition | Context | Pass | Rate | What it proves |
|-----------|---------|------|------|----------------|
| **A** | Nothing — model solves from scratch | 0/20 | 0% | M3 can't do MBPP blind |
| **B** | Failure memory — past errors shown | 3/20 | 15% | Error messages fix NameErrors |
| **B3b** | Library docs before attempt 1 | 7/20 | 35% | Docs CONFUSE the model (10% lib vs 60% non-lib) |
| **B2** | DeepSeek V4 Pro reasoning lifeline | 9/20 | 45% | Expert reasoning about *why* it failed works |
| **B3** | Web search + library docs after failure | 9/20 | 45% | +0pp — tools don't fix format mismatches |
| **B4** | Function name + example upfront | 16/20 | **80%** | Format visibility = entire 35pp gap closed |
| **C** | Oracle cheat — test assertions shown | 16/20 | 80% | Ceiling |

## Key Finding

> The 35pp gap between B2 (45%) and C (80%) was entirely a **format visibility problem.** Giving the model the function name and one example before the first attempt closes the entire gap. No expensive DeepSeek API needed. The "free format hint" (B4, 80%) beats the "paid expert reasoning" (B2, 45%). **Knowing how to talk to the model beat throwing money at it.**

## Phase 7 — Real-World Tasks with Live Web Search

The MBPP experiments above are closed-book coding. They measure what the model memorized from training data. They can't test the real thesis: can a small local model, paired with live tools, do things it was never trained to know?

We ran 3 real-world tasks (RWT). Here's the one that proves the answer is yes.

### RWT-6: Writing Code for an API the Model Never Saw

In May 2025, Anthropic released Claude Sonnet 4. The model name is `claude-sonnet-4-20250514`. Gemma 4 was trained before this date. It has no idea this model exists.

We told Gemma: *"Write a Python function that calls the Anthropic Messages API using the claude-sonnet-4-20250514 model."* Then we gave it a live web search block with the current Anthropic API docs.

Gemma wrote this:

```python
url = "https://api.anthropic.com/v1/messages"
headers = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
}
payload = {
    "model": "claude-sonnet-4-20250514",  # ← from live search, not training data
    "messages": [{"role": "user", "content": prompt}]
}
```

The model name, the endpoint, the headers — all correct. None of it was in Gemma's training data. All of it came from Tavily web search, injected into the prompt, and used correctly.

**Why this matters:** The gap between a free local model and a paid frontier model isn't just about smarts. A lot of it is about *when* the training stopped. Live tools close that gap. A 4B model running on a ThinkPad, with a web search key that costs pennies, wrote production-quality code for an API released after its training cutoff. That's the thesis.

### Full RWT Results

Three runs across 7 real-world tasks, iterating on one fix at a time:

| Run | What changed | Key finding |
|-----|-------------|-------------|
| **1** | Baseline — no override instruction | Gemma ignored Tavily. Said "I cannot browse the web." Frontier won 64 vs 43. |
| **2** | Added override: "USE THIS WEB DATA, trust it over training" | Gemma used Tavily. Correctly identified requests 2.34.2. Frontier hallucinated 2.31.0. |
| **3** | Tuned Tavily queries + replaced invalid Task 6 with post-cutoff API | **Thesis proven.** Gemma used Tavily to find `claude-sonnet-4-20250514` and wrote correct API code. |

**What we learned:** Small models default to training data unless explicitly told to trust injected context. The override instruction ("YOU MUST use the WEB CONTEXT block") was the single change that made the difference. Once the model trusted the tools, the bottleneck shifted from "model ignores web data" to "web search quality" — a solvable engineering problem.

Full results: [RWT Summary](docs/rwt-summary.md) | Source of truth: [Project Goal](https://github.com/fabiofurlano/maibs-self-improvement-framework/wiki)

## Quick Start

```bash
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework

# Requirements: Hermes Agent CLI, Python 3.10+, MiniMax M3 API access
python3 scripts/proof-run-baseline.py    # A — no memory (0%)
python3 scripts/proof-runner.py          # B — failure memory (15%)
python3 scripts/proof-run-B3b.py         # B3b — Context7-first (35%)
python3 scripts/proof-run-reasoning.py   # B2 — reasoning lifeline (45%)
python3 scripts/proof-run-B3.py          # B3 — tools (45%)
python3 scripts/proof-run-B4.py          # B4 — richer context (80%)
python3 scripts/proof-run-cheat.py       # C — oracle cheat (80%)
```

## MCP Server — Call from Any Agent

The full pipeline is exposed as a JSON-RPC 2.0 MCP tool. Start the server:

```bash
python3 maibs_mcp_server.py
# Health: http://localhost:8282/health
# MCP:    POST http://localhost:8282/mcp
```

Any MCP-compatible agent can call `solve_with_memory(task_description, task_type, test_list)` and get back `{solution, passed, attempts_used, path_taken}`. See [mcp-usage.md](mcp-usage.md) for full API docs including Tailscale remote access.

## Experience Database

Every solve — pass or fail — writes to `experience.db` (SQLite). The pass-first filter ensures tasks with zero passes see nothing (cold solve), while tasks with passes see past successes. Failures are only injected when confidence ≥ 0.8 AND a pass already exists. Solved tasks auto-append to `experiences/EXPERIENCE_INDEX.md`.

## Files

| File | Role |
|------|------|
| `scripts/proof-run-*.py` | 7 experiment conditions (A through C) |
| `scripts/oracle-runner.py` | Standalone oracle |
| `scripts/read-failures.py` | Pass-first memory filter |
| `maibs_mcp_server.py` | FastAPI MCP server (port 8282) |
| `mcp-usage.md` | MCP server API docs |
| `workflows/self-improvement-loop-task.yaml` | Archon 5-node DAG |
| `experiences/EXPERIENCE_INDEX.md` | Flat index of discovered patterns |

## Links

- Dashboard: `http://fabio-thinkpad-t14s-gen-2i.tail5f4b76.ts.net:3999/data/maibs-dashboard.html`
- Full experiment log: `~/wiki/self-improvement-loop/proof-results.md`

## License

MIT
