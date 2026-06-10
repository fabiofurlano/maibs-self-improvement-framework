# MAIBS — What This Is

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

## How It Works

7-condition experiment on 20 MBPP coding tasks. MiniMax M3 as solver. Each condition adds context before the first attempt:

| Condition | Context | Pass Rate |
|-----------|---------|-----------|
| A | Nothing | 0% |
| B | Failure memory — past errors shown | 15% |
| B3b | Library docs before attempt 1 | 35% |
| B2 | DeepSeek V4 Pro reasoning lifeline | 45% |
| B3 | Web search + library docs after failure | 45% |
| B4 | Function name + example upfront | 80% |
| C | Oracle cheat — test assertions (ceiling) | 80% |

## Quick Start

```bash
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework

python3 scripts/proof-run-baseline.py    # A — no memory (0%)
python3 scripts/proof-runner.py          # B — failure memory (15%)
python3 scripts/proof-run-B3b.py         # B3b — Context7-first (35%)
python3 scripts/proof-run-reasoning.py   # B2 — reasoning lifeline (45%)
python3 scripts/proof-run-B3.py          # B3 — tools (45%)
python3 scripts/proof-run-B4.py          # B4 — richer context (80%)
python3 scripts/proof-run-cheat.py       # C — oracle cheat (80%)
```

## MCP Server

Expose the pipeline as a callable tool for any agent:

```bash
python3 maibs_mcp_server.py
```

Health: `http://localhost:8282/health` · MCP: `POST /mcp` (JSON-RPC 2.0)

Tool: `solve_with_memory(task_description, task_type, test_list)` — returns solution + pass/fail + path taken.

## License

MIT
