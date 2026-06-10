# MAIBS — Memory-Augmented In-Context Bootstrapping System

A self-hostable, consumer-laptop-runnable framework where an LLM learns from its own experience. Given a coding task, the pipeline solves it, checks correctness with an oracle, writes the verdict to memory, and injects past successes and failures as context for future attempts. **Clone, run, watch it improve. No datacenter required.**

## The Experiment — Five Conditions, One Model

Same 20 MBPP tasks, MiniMax M3 as solver, progressively richer context:

| Condition | Context | Pass Rate |
|-----------|---------|-----------|
| **A** | None — model solves from scratch | **0%** |
| **B** | Failure memory — past errors shown | **15%** |
| **B2** | Reasoning lifeline — DeepSeek V4 Pro analyzes failures | **45%** |
| **B3** | Tools — web search + library docs after B2 failure | **45%** |
| **C** | Oracle cheat — test assertions shown (ceiling) | **80%** |

**0% → 15% → 45% → 45% → 80%**

## Key Findings

1. **Failure memory fixes NameErrors** (+15pp). The error IS the instruction.
2. **Expert reasoning triples improvement** (+30pp to B2). DeepSeek explains *why* it failed.
3. **Tools don't fix format mismatches** (+0pp to B3). Web search and library docs don't contain the exact function signatures test assertions require.
4. **35pp ceiling gap remains.** The 11 hardest tasks resist every intervention except direct test assertion visibility (C=80%).

**The bottleneck is task-specific format knowledge, not algorithm knowledge or information access.**

## How It Works — Archon DAG

```
Task → [setup] → [read-failures] → [solve] → [oracle] → [write-verdict]
                                          ↑              ↑
                                    [reasoning]    [tools-web]
                                    (DeepSeek)     (Context7/
                                                    web search)
```

## Quick Start

```bash
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework

# Requirements: Hermes Agent CLI, Archon, Python 3.10+, MiniMax M3, DeepSeek V4 Pro

python3 scripts/proof-run-baseline.py    # A — no memory (0%)
python3 scripts/proof-runner.py          # B — failure memory (15%)
python3 scripts/proof-run-reasoning.py   # B2 — reasoning lifeline (45%)
python3 scripts/proof-run-B3.py          # B3 — tools (45%)
python3 scripts/proof-run-cheat.py       # C — oracle cheat (80%)
```

## Files

| File | Role |
|------|------|
| `scripts/proof-runner.py` | Condition B — failure memory injection |
| `scripts/proof-run-baseline.py` | Condition A — clean baseline |
| `scripts/proof-run-reasoning.py` | Condition B2 — DeepSeek reasoning lifeline |
| `scripts/proof-run-B3.py` | Condition B3 — Context7 + web search tools |
| `scripts/proof-run-cheat.py` | Condition C — test assertions as ceiling |
| `scripts/oracle-runner.py` | Standalone oracle |
| `scripts/batch-runner.py` | Batch orchestrator |
| `scripts/read-failures.py` | Pass-first memory filter |
| `workflows/self-improvement-loop-task.yaml` | Archon 5-node DAG |
| `experiences/EXPERIENCE_INDEX.md` | Flat index of discovered patterns |

## License

MIT
