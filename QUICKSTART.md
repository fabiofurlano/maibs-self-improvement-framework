# MAIBS — Get a Result in 5 Minutes

You'll clone the repo, install dependencies, start the server, and run one task. No Hermes CLI needed. No local model needed. Just an OpenRouter API key (free).

## 1. Clone the repo

```bash
git clone https://github.com/fabiofurlano/maibs-self-improvement-framework.git
cd maibs-self-improvement-framework
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```
Python 3.10 or newer required.

## 3. Get a free OpenRouter API key

- Go to [openrouter.ai/keys](https://openrouter.ai/keys)
- Sign up (free, no credit card)
- Copy your API key

## 4. Start the MCP server

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here python3 maibs_mcp_server.py
```

You'll see: `MAIBS MCP Server starting on 0.0.0.0:8282`

## 5. Open the dashboard (optional)

In another terminal:
```bash
bash serve-dashboard.sh
```
Opens at http://localhost:8822. The dashboard connects to the MCP server automatically on port 8282.

## 6. Run your first task

```bash
curl -X POST http://localhost:8282/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "solve_with_memory",
      "arguments": {
        "task_description": "Write a Python function that checks if a number is prime",
        "test_list": [
          "assert is_prime(7) == True",
          "assert is_prime(10) == False",
          "assert is_prime(1) == False"
        ]
      }
    },
    "id": 1
  }'
```

## 7. See your result

```json
{
  "solution": "def is_prime(n): ...",
  "passed": true,
  "attempts_used": 2,
  "path_taken": ["attempt_1_fail", "attempt_2_pass"]
}
```

The pipeline tried once, failed, learned from the error, fixed itself, and passed. That's the whole point of MAIBS.

---

## What just happened

1. The model attempted to solve your task
2. The oracle ran your test assertions and found it failed
3. The pipeline showed the model its own error
4. The model fixed the error and passed
5. The experience was saved to `experiences/EXPERIENCE_INDEX.md`

Next time you ask a similar task, the pipeline remembers what worked.

## Switching models

```bash
# Use a different free model
OPENROUTER_MODEL=mistralai/mistral-3-small:free \
  OPENROUTER_API_KEY=sk-or-v1-your-key \
  python3 maibs_mcp_server.py
```

Free models available: `google/gemma-3-4b-it:free` (default), `mistralai/mistral-3-small:free`, `deepseek/deepseek-chat:free`.

## Optional: Run with a local model

If you have Hermes Agent installed, the server auto-detects it and uses `hermes -z` instead of OpenRouter. No API key needed.

## Optional: Run the full experiment suite

See the [README](README.md) for the 7-condition experiment table. Each script is in `scripts/`. They require Hermes CLI + MiniMax M3 API access.

## License

MIT
