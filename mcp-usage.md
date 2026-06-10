# MAIBS MCP Server — Usage Guide

## Overview

The MAIBS MCP server exposes the full self-improvement pipeline as a single callable tool: `solve_with_memory`. Any MCP-compatible agent can connect and delegate a coding task.

**MCP 2024-11-05 compliant.** Tested with: `curl`, `python requests`, Hermes Agent (native MCP client).

## Quick Start

```bash
# Start the server
python3 maibs_mcp_server.py

# With API key auth
MAIBS_API_KEY=sk-your-key python3 maibs_mcp_server.py
```

Server runs on:
- **Local:** `http://127.0.0.1:8282`
- **Tailscale (remote agents):** `http://fabio-thinkpad-t14s-gen-2i.tail5f4b76.ts.net:8282`

Health check: `GET /health`. MCP endpoint: `POST /mcp`. SSE session: `GET /mcp`.

## Default Solver

The server uses the **local Gemma 4 E4B** (free, CPU-only laptop model) by default. Falls back to MiniMax M3 via Hermes CLI if llama-server is not running. The response includes a `solver` field indicating which model was used.

## MCP Protocol

Standard MCP 2024-11-05 over HTTP. Single endpoint: `POST /mcp`.

### Client Config — Claude Code CLI

```bash
claude mcp add-json maibs '{"type":"http","url":"http://localhost:8282/mcp"}'
```

Or in `.mcp.json`:

```json
{
  "mcpServers": {
    "maibs": {
      "type": "http",
      "url": "http://localhost:8282/mcp"
    }
  }
}
```

### Client Config — Hermes Agent

In `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  maibs:
    url: "http://localhost:8282/mcp"
    timeout: 300
    connect_timeout: 30
```

Tools appear as `mcp_maibs_solve_with_memory`. Restart gateway to discover.

### Client Config — Codex CLI

```bash
codex mcp add maibs --url http://localhost:8282/mcp
```

### Client Config — Antigravity (via Claude Desktop config)

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "maibs": {
      "url": "http://localhost:8282/mcp"
    }
  }
}
```

### Remote (Tailscale)

Replace `localhost:8282` with `fabio-thinkpad-t14s-gen-2i.tail5f4b76.ts.net:8282` in any config above.

## Input Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `task_description` | ✅ | string | The coding task description |
| `task_type` | ❌ | string | `coding`, `general`, or `benchmark` (default: `coding`) |
| `test_setup` | ❌ | string | Setup code to run before assertions (imports, helpers) |
| `test_list` | ❌ | array of strings | Assert statements to validate the solution |

## Output Format

```json
{
  "solution": "def max_length_list(lst): ...",
  "passed": true,
  "attempts_used": 2,
  "path_taken": ["experience_index", "attempt_1_fail", "attempt_2_pass"],
  "error": "",
  "solver": "gemma-4-e4b-local",
  "attempt_details": [
    {"attempt": 1, "error": "NameError: name 'max_length_list' is not defined", "time_s": 11.7},
    {"attempt": 2, "error": "", "time_s": 18.0}
  ]
}
```

### path_taken Values

| Value | Meaning |
|-------|---------|
| `experience_index` | Past patterns from EXPERIENCE_INDEX.md were injected |
| `context7:<lib>` | Library documentation found for `<lib>` |
| `attempt_1_pass` | Solved on first attempt |
| `attempt_1_fail` | First attempt failed |
| `attempt_2_pass` | Solved on second attempt (failure memory) |
| `attempt_2_fail` | Second attempt failed |
| `attempt_3_pass_reasoning` | Solved after DeepSeek V4 Pro reasoning |
| `attempt_3_fail` | Third attempt failed |
| `attempt_4_pass` | Solved after web search fallback |
| `attempt_4_fail_all_exhausted` | All attempts exhausted, still failing |

## Internal Pipeline

```
Task → [EXPERIENCE_INDEX] → [Gemma 4 E4B] → Attempt 1
                                    ↓ FAIL
                          [Failure memory] → Attempt 2
                                    ↓ FAIL
                          [DeepSeek reasoning] → Attempt 3
                                    ↓ FAIL
                          [Web search] → Attempt 4
                                    ↓
                          Result (pass/fail + path)
```

Default solver: local Gemma 4 E4B. DeepSeek reasoning lifeline uses Hermes CLI `deepseek-v4-pro`. All attempts use the local model except escalation.

## Authentication

Set `MAIBS_API_KEY` environment variable when starting the server. Clients must send the matching key in the `X-API-Key` header.

Without `MAIBS_API_KEY`, the server runs in open mode (no auth required).

## License

MIT
