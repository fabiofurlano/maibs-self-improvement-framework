# MAIBS — Memory-Augmented In-Context Bootstrapping System

> **A free local model, plus memory of its own past work, plus the right tools, performs like a proprietary model.**
> You call it over MCP. The expensive cloud models are fallback and orchestration only — never the engine.

A 4B-parameter model running on a laptop, with a web search key that costs pennies, wrote production-quality code for an API released after its training cutoff. That's the thesis. This repo proves it.

---

## ⚠️ Vibe Coder Alert

Built by one person, no team, no lab, no budget, running on a ThinkPad in Italy. Probably has bugs. PRs welcome.

---

## The Three Proofs

### 1. Format Hints Beat Expensive Reasoning (MBPP)

Same 20 coding tasks, same model. Each condition adds more context before the first attempt:

| Condition | What was added | Pass rate | Cost |
|---|---|---|---|
| A | Nothing | 0% | Free |
| B | Past failure memory | 15% | Free |
| B2 | DeepSeek V4 Pro reasoning lifeline | 45% | Paid API |
| B4 | Function name + one example | **80%** | **Free** |
| C | Oracle cheat (test assertions shown) | 80% | Ceiling |

**Finding:** The 35pp gap between paid reasoning (45%) and ceiling (80%) was entirely a format visibility problem. Knowing how to talk to the model beat throwing money at it.

### 2. Live Tools Close the Training Cutoff Gap (RWT)

Gemma 4 was trained before May 2025. It has no idea `claude-sonnet-4-20250514` exists.

We gave it a live Tavily web search block with current Anthropic API docs and said: *"Write code that calls this model."*

Gemma wrote correct, production-quality code — correct endpoint, correct headers, correct model name. All from live search. None from training data.

**Why this matters:** A lot of the gap between free local models and paid frontier models isn't about smarts. It's about *when the training stopped*. Live tools close that gap.

### 3. Multi-Role Pipeline Works (Phase D2)

A full pipeline where a cloud orchestrator plans the steps, a local Gemma executes each one, an evaluator checks compliance, and a compressor keeps context clean between steps:

| Phase | What | Result |
|---|---|---|
| A | Evaluator node | 5/5 violations caught, 0 false rejections |
| B | Context compressor + integration manifest | 4/5 preserved, floor 21% |
| C | Orchestrator loop (5-step task) | All steps passed, max 2,881 chars context |
| D2 | Full proof run on GPU (8-step web scraper) | **5/8 steps passed**, zero false evaluator rejections, compressor working between all steps |

**D2 v7 result:** Steps 1-5 all passed first try. Step 6 failed at syntax (4B model limit on complex integration code — not architecture). 114 seconds total. Pipeline is mechanically correct.

---

## Architecture

```
USER INPUT
    ↓
INTENT CLASSIFIER (Gemma) → clarify / plan / execute
    ↓
SAFETY GATE (Gemma) — structural check
    ↓
MEMORY — past solutions + Tavily web snippet
    ↓
ORCHESTRATOR (cloud) — breaks task into steps
    ↓
STEP LOOP:
  EXECUTOR (Gemma) → ORACLE → EVALUATOR → COMPRESSOR
  Max 3 iterations per step. Then reasoning lifeline. Then stop.
  Integration manifest passed every step — never compressed.
    ↓
FINAL PRODUCT EVALUATION
    ↓
EXPERIENCE DB — save verified solution
```

**Key invariants:**
- Gemma is always the Executor. Cloud models plan or rescue only.
- Evaluator always reads ORIGINAL criteria — never compressed context.
- Max 3 iterations per step. Hard cap.
- Integration manifest never compressed.

---

## Quick Start

```bash
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework

# Start the MCP server
python3 maibs_mcp_server.py --port 8282

# Health check
curl http://localhost:8282/health
```

Any MCP-compatible agent can call `solve_with_memory(task_description, task_type, test_list)` and get back `{solution, passed, attempts_used, path_taken}`.

For multi-step tasks: `solve_multistep(task_description, criteria)` runs the full pipeline with orchestrator, executor, evaluator, and compressor.

---

## The Models

| Model | Role | Cost |
|---|---|---|
| **Gemma 4 E4B** (local / GPU) | Primary solver. Does all the work. | Free / cheap GPU |
| **DeepSeek V4 Pro / Claude Sonnet** (OpenRouter) | Reasoning lifeline + orchestrator. Called rarely. | Pay-per-use |

---

## Files

| File | Role |
|---|---|
| `maibs_mcp_server.py` | FastAPI MCP server — full pipeline |
| `scripts/proof-run-*.py` | MBPP experiment conditions (A through C) |
| `scripts/rwt-runner-v3.py` | Real-world task benchmark runner |
| `scripts/phase_d2_runner.py` | Multi-role pipeline proof runner |
| `experiences/EXPERIENCE_INDEX.md` | Flat index of discovered patterns |
| `projects/maibs/` | Phase results, raw data, rubrics |
| `dashboard/` | Live pipeline monitor UI |

---

## Full Experiment History

| Phase | What | Status |
|---|---|---|
| 1 | Memory loop (0%→15%) | ✅ |
| 2 | Reasoning lifeline (15%→45%) | ✅ |
| 3 | Tools on MBPP — no gain | ✅ |
| 4 | Format hint breakthrough (80%) | ✅ |
| 5 | MCP server live | ✅ |
| 6 | MBPP frozen, RWT proven | ✅ |
| 7 | Multi-role pipeline built (A–C) | ✅ |
| D | Proof test on GPU | ✅ 5/8 steps |
| 8 | Publish + NoLabAI post | 🔄 Now |
| 9 | Human-in-the-loop | ⬜ |
| 10 | Fine-tune on experience DB | ⬜ |

---

## What "Done" Looks Like

A developer anywhere:
1. Clones the repo
2. Follows QUICKSTART.md
3. Connects their coding agent via MCP
4. Gets a free local-model solver that gets better the more they use it
5. Can export accumulated experience as training data

---

## License

MIT
