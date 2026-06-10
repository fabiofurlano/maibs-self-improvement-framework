# MAIBS Dashboard

Single-file interactive dashboard for the MAIBS pipeline. Open in any browser — no build, no server, no dependencies beyond the MCP server running on port 8282.

## Quick Launch

```bash
# Terminal 1: start the MCP server
OPENROUTER_API_KEY=sk-or-v1-your-key python3 maibs_mcp_server.py

# Terminal 2: serve the dashboard
bash serve-dashboard.sh
```

Opens at http://localhost:8822. The dashboard calls the MCP server on port 8282 — no manual config needed.

## Features

- **Setup** — Hardware requirements, download links for local Gemma 4, OpenRouter API key + model dropdowns, one-click Quick Test
- **Settings** — Toggle pipeline layers, set max attempts, configure API keys
- **Task Tester** — Type a coding task + tests, hit Run, see pipeline stages in real time (green=pass, red=fail, gold=active)
- **Experience** — Browse the distilled experience index, search, export to JSONL
- **Connect Agent** — Copy-paste MCP config blocks for Claude, Codex, or Gemini

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

- MAIBS MCP server running on port 8282 (`python3 maibs_mcp_server.py`)
- Any modern browser
- No Node.js, no build step, no framework

## Design

- Dark theme (`#08090a` canvas, `#191a1b` panels)
- Gold `#c9a84c` / green `#5a9e6a` / red `#c96a5a` accent system
- Inter (UI) + JetBrains Mono (code) fonts
- Zero external JS dependencies
