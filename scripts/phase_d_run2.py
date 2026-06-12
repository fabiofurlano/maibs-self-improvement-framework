#!/usr/bin/env python3.10
"""Phase D Run 2 — DeepSeek V4 Pro bare, single prompt, no tools."""

import sys, os, json, time, urllib.request, urllib.error

# Load API key
API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not API_KEY:
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

if not API_KEY:
    print("ERROR: No OPENROUTER_API_KEY found")
    sys.exit(1)

TASK = (
    "Build a working web scraper: fetch a public webpage using requests, "
    "extract all hyperlinks using BeautifulSoup, filter to external links only, "
    "write results to a CSV file, include error handling for bad URLs, "
    "write a usage README."
)

SYSTEM_PROMPT = """You are a senior Python engineer. Write complete, production-quality code. 
Output ALL files needed. Do not skip error handling or the README.
Respond with the complete code for scraper.py and README.md in clearly labeled sections."""

USER_PROMPT = f"""Build a working web scraper with these EXACT requirements:

1. Fetch a public webpage using the `requests` library (include User-Agent header)
2. Parse the HTML with `BeautifulSoup` from bs4
3. Extract all hyperlinks (<a href="...">)
4. Filter to EXTERNAL links only (different domain from the target URL)
5. Write filtered results to a CSV file with columns: url, link_text, target_url
6. Include error handling: bad URLs (timeout, connection error), missing pages (404), non-HTML responses
7. Write a usage README.md with install instructions, usage example, and output format

Write ALL the code. Output scraper.py first, then README.md. Label each section clearly."""

print("=" * 70, flush=True)
print("PHASE D — RUN 2: DeepSeek V4 Pro bare (single prompt, no tools)", flush=True)
print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print("=" * 70, flush=True)

t0 = time.time()
try:
    payload = json.dumps({
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "MAIBS-PhaseD",
        },
    )

    print("Calling DeepSeek via OpenRouter...", flush=True)
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - t0

    raw_output = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {})
    model = data.get("model", "unknown")

    print(f"\nDone in {elapsed:.0f}s", flush=True)
    print(f"Model: {model}", flush=True)
    print(f"Tokens: {tokens}", flush=True)
    print(f"Output length: {len(raw_output)} chars", flush=True)
    print(f"\n--- RAW OUTPUT (first 2000 chars) ---", flush=True)
    print(raw_output[:2000], flush=True)
    print(f"... ({len(raw_output)} total chars)", flush=True)

    # Save
    raw_path = "/tmp/maibs-self-improvement-framework/projects/maibs/phase-d-run2-raw.json"
    with open(raw_path, "w") as f:
        json.dump({
            "task": TASK,
            "elapsed_s": elapsed,
            "model": model,
            "tokens": tokens,
            "output_length": len(raw_output),
            "raw_output": raw_output,
        }, f, indent=2, default=str)
    print(f"\nRaw saved to {raw_path}", flush=True)

except Exception as e:
    elapsed = time.time() - t0
    print(f"\nFAILED after {elapsed:.0f}s: {e}", flush=True)
    import traceback
    traceback.print_exc()
