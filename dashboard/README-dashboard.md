# MAIBS Dashboard

Single-file interactive dashboard for the MAIBS (Memory-Augmented In-Context Bootstrapping System) pipeline. Open `index.html` in any browser — no build, no server, no dependencies.

## Features

- **Settings** — Configure inference backends (Local Gemma, OpenRouter), pipeline layers (7 stages with toggles), max attempts slider, and external tool API keys (Tavily, Context7). Reads/writes `~/.maibs/config.yaml` via the MAIBS MCP server.
- **Setup** — First-time configuration wizard: download the local model from HuggingFace, find HuggingFace speedup techniques from the wiki, configure OpenRouter API key with model dropdowns, and run a one-click Quick Test.
- **Task Tester** — Type a coding task and hit Run. The dashboard calls `solve_with_memory` on the live MCP server (port 8282) and shows the real-time pipeline path with color-coded stages.
- **Experience** — Browse the distilled experience index (reads from `experience.db`). Search, filter, and export to JSONL.
- **Connect Agent** — Copy-paste MCP config blocks for Claude Desktop, Codex CLI, or Gemini CLI.

## One-Command Launch

```bash
# 1. Start the MCP server
cd ~/.hermes/scripts && python3.10 maibs_mcp_server.py &

# 2. Open the dashboard
xdg-open /tmp/maibs-self-improvement-framework/dashboard/index.html
```

Or open directly from the repo clone:
```bash
open https://github.com/fabiofurlano/maibs-self-improvement-framework/blob/main/dashboard/index.html
# (download raw HTML and open locally for full API access)
```

## Architecture

```
dashboard/index.html  ──fetch──►  MCP Server (:8282)
   │                                    │
   │  Settings ──PUT /api/config──►  ~/.maibs/config.yaml
   │  Run ──POST /mcp─────────────►  solve_with_memory()
   │  Experience ──GET /api/experiences──►  experience.db
   │  Test Conn ──POST /api/tools/test──►  Tavily + Context7
```

## Requirements

- MAIBS MCP server running on port 8282 (`python3.10 ~/.hermes/scripts/maibs_mcp_server.py`)
- Browser with CORS disabled or served from the same origin (open locally as `file://` for development)

## Design

- Dark theme (`#08090a` canvas, `#191a1b` panels)
- Gold `#c9a84c` / green `#5a9e6a` / red `#c96a5a` accent system
- Inter (UI) + JetBrains Mono (code) fonts
- No external JS dependencies, no build step
