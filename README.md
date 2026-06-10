# MAIBS — Memory-Augmented In-Context Bootstrapping System

A self-hostable, consumer-laptop-runnable framework where an LLM learns from its own experience. Given a coding task, the pipeline solves it, checks correctness with an oracle, writes the verdict to memory, and injects past successes and failures as context for future attempts. **Clone, run, watch it improve. No datacenter required.**

## The Experiment — Three Conditions, One Model

Same 20 MBPP tasks, same MiniMax M3 model, three different memory strategies:

| Condition | Memory | Pass Rate |
|-----------|--------|-----------|
| **A** | None — model solves from scratch | **0%** |
| **B** | Failure memory — model sees its own past errors before re-attempting | **15%** |
| **C** | Oracle cheat — test assertions shown as hints (ceiling) | **80%** |

**Key insight:** Failure memory alone captures 19% of the possible improvement (15pp out of 80pp of ceiling). NameErrors flip because the error message IS the fix instruction (wrong function name → correct function name). But most tasks need richer memory — showing correct examples, function signatures, or test assertions — to close the gap.

## How It Works — 5-Node Archon DAG

```
Task → [setup] → [read-failures] → [solve] → [oracle] → [write-verdict]
```

1. **setup** — Loads the MBPP task JSON, writes metadata to temp files
2. **read-failures** — Queries `experience.db` for past attempts on this task. Uses a **pass-first filter**: 0-pass tasks see nothing (cold solve), tasks with passes see past successes first, failures only if confidence ≥ 0.8
3. **solve** — Builds the prompt (problem + memory injection), calls the LLM via Hermes CLI, saves output to `/tmp/sil-solve-output.txt`
4. **oracle** — Extracts code from the LLM output, runs it against MBPP test assertions. Result: `ORACLE_PASS` or `ORACLE_FAIL`
5. **write-verdict** — Appends the attempt (code, outcome, error) to `experience.db`. Retry tasks only — heldout tasks skip this node to prevent contamination

All LLM output flows through temp files (`/tmp/sil-*.txt`) — zero YAML variable interpolation, avoiding triple-quote and backtick bugs that plagued earlier designs.

## Quick Start

```bash
# Clone
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework

# Requirements
# - Hermes Agent CLI (hermes -z)
# - Archon workflow engine
# - Python 3.10+
# - MiniMax M3 API access (or swap model in scripts/proof-runner.py)

# Run the 20-task proof
python3 scripts/proof-run-baseline.py    # Condition A — no memory
python3 scripts/proof-runner.py          # Condition B — with failure memory
python3 scripts/proof-run-cheat.py       # Condition C — oracle cheat (ceiling)

# Results are saved to JSON and experience.db
```

## Files

| File | Role |
|------|------|
| `scripts/proof-runner.py` | Condition B — injects past failures as memory, runs oracle, counts flips |
| `scripts/proof-run-baseline.py` | Condition A — clean baseline, no memory |
| `scripts/proof-run-cheat.py` | Condition C — shows test assertions as hints (ceiling) |
| `scripts/oracle-runner.py` | Standalone oracle — runs test assertions against LLM output |
| `scripts/batch-runner.py` | Batch orchestrator — runs multiple tasks through the full DAG |
| `scripts/read-failures.py` | Pass-first memory filter — queries experience.db, gates failure injection |
| `workflows/self-improvement-loop-task.yaml` | Archon DAG — 5-node pipeline for a single task |

## Architecture Decisions

- **Pass-first filter prevents memory poisoning.** Showing failures to tasks the model has never solved makes them WORSE. Cold tasks get clean slates.
- **Foreground execution > background.** Background Archon runs hit 30-min gateway timeouts. Each task takes ~10s in foreground — 20 tasks = ~4 minutes.
- **Temp files over variable interpolation.** YAML triple-quote handling in Archon is fragile. Sidecar files (`/tmp/sil-*.txt`) are deterministic.
- **MiniMax M3 as baseline model.** 4.5% heldout pass rate on MBPP gives ample headroom to measure improvement.

## Roadmap

| Phase | What | Hypothesis |
|-------|------|------------|
| ✅ **1. Repo ships** | Public release with proof runner | Memory alone = 15% |
| 🔜 **2. Reasoning lifeline** | DeepSeek V4 Pro API call for hard tasks | Memory + reasoning > 15% |
| 🔜 **3. Web search + Context7** | Tool-augmented agent for coding tasks | Memory + tools > reasoning alone? |

Each phase adds one variable and we measure the flip rate. The table builds up over time — that's the story.

## License

MIT
