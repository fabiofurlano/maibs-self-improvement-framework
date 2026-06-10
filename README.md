# MAIBS — Memory-Augmented In-Context Bootstrapping System

A self-hostable, consumer-laptop-runnable framework where an LLM learns from its own experience. Given a coding task, the pipeline solves it, checks correctness with an oracle, writes the verdict to memory, and injects past successes and failures as context for future attempts. **Clone, run, watch it improve. No datacenter required.**

## The Experiment — Four Conditions, One Model

Same 20 MBPP tasks, MiniMax M3 as solver, three different memory strategies + one reasoning lifeline:

| Condition | Memory | Pass Rate |
|-----------|--------|-----------|
| **A** | None — model solves from scratch | **0%** |
| **B** | Failure memory — model sees its own past errors before re-attempting | **15%** |
| **B2** | Reasoning lifeline — DeepSeek V4 Pro analyzes double-failures, injects reasoning | **45%** |
| **C** | Oracle cheat — test assertions shown as hints (ceiling) | **80%** |

**Progress: 0% → 15% → 45% → 80%**

- **B (+15pp):** NameError correction — the error message IS the instruction
- **B2 (+30pp):** DeepSeek reasoning — explains *why* it failed and *how* to fix it
- **C (+35pp remaining):** Test assertions — function names + expected I/O (ceiling)
- **35pp gap to C:** Untapped improvement with tools (Phase 3)

## How It Works — 5-Node Archon DAG + Reasoning Lifeline

```
Task → [setup] → [read-failures] → [solve] → [oracle] → [write-verdict]
                                          ↑
                                    [reasoning-lifeline]
                                    (DeepSeek V4 Pro on 2nd failure)
```

1. **setup** — Loads the MBPP task JSON, writes metadata to temp files
2. **read-failures** — Queries `experience.db` for past attempts. Uses a **pass-first filter**: 0-pass tasks see nothing (cold solve), tasks with passes see past successes first, failures only if confidence ≥ 0.8
3. **solve** — Builds the prompt (problem + memory injection), calls the LLM via Hermes CLI, saves output to `/tmp/sil-solve-output.txt`
4. **reasoning-lifeline** (NEW — Phase 2) — When a task fails twice: calls DeepSeek V4 Pro with the problem + both failed attempts, gets expert analysis back, injects it into the third attempt
5. **oracle** — Extracts code from the LLM output, runs it against MBPP test assertions. Result: `ORACLE_PASS` or `ORACLE_FAIL`
6. **write-verdict** — Appends the attempt (code, outcome, error) to `experience.db`. Retry tasks only — heldout tasks skip this node to prevent contamination

## Quick Start

```bash
# Clone
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework

# Requirements
# - Hermes Agent CLI (hermes -z)
# - Archon workflow engine
# - Python 3.10+
# - MiniMax M3 API access (or swap model in scripts)
# - DeepSeek V4 Pro API access (for B2 reasoning lifeline)

# Run the 20-task proof
python3 scripts/proof-run-baseline.py    # Condition A — no memory (0%)
python3 scripts/proof-runner.py          # Condition B — with failure memory (15%)
python3 scripts/proof-run-reasoning.py   # Condition B2 — reasoning lifeline (45%)
python3 scripts/proof-run-cheat.py       # Condition C — oracle cheat (80%)

# Results are saved to JSON and experience.db
```

## Files

| File | Role |
|------|------|
| `scripts/proof-runner.py` | Condition B — injects past failures as memory |
| `scripts/proof-run-baseline.py` | Condition A — clean baseline, no memory |
| `scripts/proof-run-reasoning.py` | Condition B2 — DeepSeek reasoning lifeline for double-failures |
| `scripts/proof-run-cheat.py` | Condition C — shows test assertions as hints (ceiling) |
| `scripts/oracle-runner.py` | Standalone oracle — runs test assertions against LLM output |
| `scripts/batch-runner.py` | Batch orchestrator — runs multiple tasks through the full DAG |
| `scripts/read-failures.py` | Pass-first memory filter — queries experience.db |
| `workflows/self-improvement-loop-task.yaml` | Archon 5-node DAG pipeline |
| `experiences/EXPERIENCE_INDEX.md` | Flat index of discovered patterns |
| `experiences/coding/nameerror-fix.md` | NameError fix pattern detail |
| `experiences/coding/reasoning-lifeline.md` | DeepSeek reasoning lifeline pattern detail |
| `experiences/coding/assertionerror-limit.md` | AssertionError limitation detail |

## Architecture Decisions

- **Pass-first filter prevents memory poisoning.** Showing failures to tasks the model has never solved makes them WORSE.
- **Foreground execution > background.** Each task takes ~10s. 20 tasks = ~5 minutes — no timeout risk.
- **Temp files over variable interpolation.** YAML triple-quote handling in Archon is fragile. Sidecar files are deterministic.
- **Reasoning lifeline on second failure, not first.** One API call per double-fail task — 17 calls produced 6 new passes (35% efficiency).

## Roadmap

| Phase | What | Result |
|-------|------|--------|
| ✅ **1. Repo ships** | Public release with proof runner | Memory alone = **15%** |
| ✅ **2. Reasoning lifeline** | DeepSeek V4 Pro for double-failures | Memory + reasoning = **45%** |
| 🔜 **3. Web search + Context7** | Tool-augmented agent for coding tasks | Memory + tools = **?%** |

Each phase adds one variable and we measure the flip rate. The table builds up over time — that's the story.

## License

MIT
