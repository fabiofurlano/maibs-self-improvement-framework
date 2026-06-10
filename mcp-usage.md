# MAIBS MCP Server — Usage Guide

## Overview

The MAIBS MCP server exposes the full self-improvement pipeline as a single callable tool: `solve_with_memory`. Any MCP-compatible agent can connect and delegate a coding task.

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

Health check: `GET /health`. MCP endpoint: `POST /mcp`.

## MCP Protocol

Standard JSON-RPC 2.0 over HTTP. Single endpoint: `POST /mcp`.

### Initialize

```bash
curl -X POST http://127.0.0.1:8282/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1}'
```

### List Tools

```bash
curl -X POST http://127.0.0.1:8282/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2}'
```

### Call solve_with_memory

```bash
curl -X POST http://127.0.0.1:8282/mcp \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: sk-your-key' \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "solve_with_memory",
      "arguments": {
        "task_description": "Write a function to find the list with maximum length using lambda",
        "task_type": "coding",
        "test_list": [
          "assert max_length_list([[0], [1,3], [5,7]]) == [5,7]"
        ]
      }
    },
    "id": 99
  }'
```

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
Task → [EXPERIENCE_INDEX] → [Context7 if library] → Attempt 1
                                                        ↓ FAIL
                                              [Failure memory] → Attempt 2
                                                        ↓ FAIL
                                              [DeepSeek reasoning] → Attempt 3
                                                        ↓ FAIL
                                              [Web search] → Attempt 4
                                                        ↓
                                              Result (pass/fail + path)
```

On success, the pipeline automatically:
- Appends an entry to `experiences/EXPERIENCE_INDEX.md`
- Writes a detail file with the solution and path taken for future reference

## Authentication

Set `MAIBS_API_KEY` environment variable when starting the server. Clients must send the matching key in the `X-API-Key` header.

Without `MAIBS_API_KEY`, the server runs in open mode (no auth required).

## Connecting Another Agent

Any MCP-compatible agent can connect by adding to its MCP server config:

```json
{
  "mcpServers": {
    "maibs": {
      "url": "http://127.0.0.1:8282/mcp",
      "headers": {
        "X-API-Key": "sk-your-key"
      }
    }
  }
}
```

For remote agents over Tailscale:

```json
{
  "mcpServers": {
    "maibs": {
      "url": "http://fabio-thinkpad-t14s-gen-2i.tail5f4b76.ts.net:8282/mcp",
      "headers": {
        "X-API-Key": "sk-your-key"
      }
    }
  }
}
```

No Funnel or Cloudflare needed — Tailscale mesh connects directly.

## Requirements

- Python 3.10+
- `fastapi`, `uvicorn`, `ddgs`
- Hermes Agent CLI (`hermes -z`)
- MiniMax M3 API access (via `hermes -z -m MiniMax-M3 --provider minimax`)
- DeepSeek V4 Pro API access (for reasoning lifeline, via `hermes -z -m deepseek-v4-pro --provider opencode-go`)
- Internet access (for DuckDuckGo web search fallback)

## License

MIT
