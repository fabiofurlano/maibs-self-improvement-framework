#!/usr/bin/env python3.10
"""Phase B gate test — Context Engineer node.

Tests compress_context() against 5 real RWT outputs:
  1. Compress each with a real next-step goal
  2. Measure compression ratio (input chars → output chars)
  3. Test: Gemma answers next-step questions using compressed vs full context
  4. Find the safe compression floor

Target: identify the ratio where information loss starts hurting success.
"""
import sys, os, time, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from maibs_mcp_server import compress_context, call_gemma

# ═══════════════════════════════════════════════════════
#  Test cases: (label, raw_output, next_step_goal, fact_check_question, expected_keywords)
# ═══════════════════════════════════════════════════════

TESTS = [
    # ── Test 1: RWT-1 run-3 — Live Docs Lookup ──
    (
        "RWT-1: Requests changelog",
        """Based on the provided web context, here is the summary of the changes in the Python `requests` library.

***

### Current Version Number
The provided web context does not specify the current version number of the `requests` library.

### Summary of Key Changes
The latest release focuses primarily on internal type adjustments and improvements to typing consistency within the library:

*   **Headers Input Type:** The `headers` input type was moved back to `Mapping` to prevent invariance issues that arose when using `MutableMapping` and inferred dictionary types.
*   **JSON Input Type:** The accepted input type for `json` was widened from being restricted to `dict` and `list` to the broader `Mapping` type.
*   **Internal Code Adjustments:** The release notes indicate that `Request.headers.update()` may require typing narrowing within the library's internal code.

### Python Usage Example
Since the changes detailed in the changelog are primarily internal type adjustments (e.g., moving from `dict` to `Mapping`), they do not introduce a new, user-facing feature that requires a unique usage example. A standard request remains the primary way to interact with the library.

```python
import requests

# Standard usage example
try:
    response = requests.get('https://jsonplaceholder.typicode.com/todos/1')
    response.raise_for_status()
    print("Status Code:", response.status_code)
    print("JSON Data:", response.json())
except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")
```

### Source URL
The information was retrieved from the official requests changelog:
`https://data.safetycli.com/packages/pypi/requests/changelog`""",
        "Write a pip command to upgrade the requests library and a brief note about what changed in the latest release.",
        "What types were changed in the latest requests release? Answer in one sentence.",
        ["Mapping", "MutableMapping", "headers", "json"],
    ),
    
    # ── Test 2: RWT-2 run-1 — Memory Carry-Over ──
    (
        "RWT-2: Email extraction",
        """def extract_domain(email: str) -> str:
    \"\"\"
    Extract the domain part of an email address.
    \"\"\"
    try:
        domain = email.split('@')[1]
        return domain
    except IndexError:
        return ""

# Example Usage:
# print(extract_domain('user@example.com'))
# print(extract_domain('another.user123@sub.domain.net'))
# print(extract_domain('invalid-email'))""",
        "Write extract_username(email) that returns the part before the @ symbol, using the same split approach.",
        "Write a Python function extract_username(email) that returns the part before @. Use the same technique as extract_domain.",
        ["split('@')", "0]", "@", "extract_username"],
    ),
    
    # ── Test 3: RWT-4 run-3 — Web Extraction ──
    (
        "RWT-3: HTTP methods summary",
        """As Gemma, I have analyzed the provided `WEB CONTEXT` from the Python `requests` library Quickstart documentation.

Based *only* on the information contained in the provided extract, here is the structured summary:

***

### 📚 Requests Library Quickstart Summary

#### 1. Most Common HTTP Methods Shown
The provided web context snippet only explicitly demonstrates one HTTP method.

*   **GET**

#### 2. Examples for Each Method
**GET**
```python
r = requests.get('https://api.github.com/events')
```

#### 3. SSL Verification Warnings or Notes
The provided web context extract does not contain any specific warnings or notes regarding SSL verification.""",
        "Write a POST request example using the same requests library pattern shown above.",
        "Write a Python function that makes a POST request to https://httpbin.org/post with JSON data {'key': 'value'} using the requests library.",
        ["requests.post", "json=", "httpbin", "key"],
    ),
    
    # ── Test 4: RWT-5 run-1 — Bug-Fix with History ──
    (
        "RWT-4: Middle-third slicing",
        """def get_middle_third(items: list) -> list:
    \"\"\"
    Returns the middle third of a list.
    For a list of length N, returns elements from index N//3 to index 2*N//3 (inclusive).
    \"\"\"
    n = len(items)
    if n == 0:
        return []

    start_index = n // 3
    end_index = (2 * n // 3) + 1
    return items[start_index:end_index]""",
        "Write get_first_third(items) that returns the first third using the same slicing pattern from get_middle_third.",
        "Write a Python function get_first_third(items) that returns the first N//3 elements using the same slicing approach as get_middle_third.",
        ["get_first_third", "items[:", "//3", "return"],
    ),
    
    # ── Test 5: RWT-6 run-3 — Anthropic Messages API ──
    (
        "RWT-5: Claude API call",
        """def call_claude(prompt: str) -> str:
    \"\"\"Calls the Anthropic Messages API using the claude-sonnet-4-20250514 model.\"\"\"
    API_KEY = "YOUR_ANTHROPIC_API_KEY"
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2048,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("content") and data["content"][0].get("text"):
            return data["content"][0]["text"]
        else:
            return "Error: Response structure was unexpected or empty."
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")""",
        "Add a temperature parameter to call_claude. The new function should accept temperature as a float with default 0.7.",
        "What model name and API version does call_claude use? Answer in one line.",
        ["claude-sonnet-4-20250514", "2023-06-01"],
    ),
]

# ═══════════════════════════════════════════════════════
#  Run
# ═══════════════════════════════════════════════════════

print("=" * 72)
print("  PHASE B GATE TEST — Context Engineer Node")
print("  5 RWT outputs → compress → validate preservation")
print("=" * 72)
print()

results = []

for label, raw_output, next_goal, check_question, expected_kw in TESTS:
    input_size = len(raw_output)
    print(f"─── {label} ───")
    print(f"  Input size: {input_size:,} chars")
    print(f"  Next step goal: {next_goal[:80]}...")
    
    # ── Compress ──────────────────────────────
    t0 = time.time()
    compressed = compress_context(raw_output, next_goal)
    compress_time = time.time() - t0
    
    output_size = len(compressed)
    ratio = (output_size / input_size * 100) if input_size > 0 else 0
    print(f"  Compressed: {output_size:,} chars ({ratio:.0f}% of input) in {compress_time:.1f}s")
    
    # ── Show compressed content ───────────────
    preview = compressed[:200].replace("\n", "\\n")
    print(f"  Preview: {preview}...")
    
    # ── Baseline: Gemma answers using FULL context ──
    baseline_prompt = f"Context:\n{raw_output}\n\nQuestion: {check_question}\n\nAnswer in one sentence. Be specific."
    baseline_answer, t_baseline = call_gemma(baseline_prompt, timeout=60)
    
    # ── Test: Gemma answers using COMPRESSED context ──
    test_prompt = f"Context:\n{compressed}\n\nQuestion: {check_question}\n\nAnswer in one sentence. Be specific."
    test_answer, t_test = call_gemma(test_prompt, timeout=60)
    
    # ── Score: how many expected keywords appear ──
    baseline_kw_found = sum(1 for kw in expected_kw if kw.lower() in baseline_answer.lower())
    test_kw_found = sum(1 for kw in expected_kw if kw.lower() in test_answer.lower())
    total_kw = len(expected_kw)
    
    baseline_ok = baseline_kw_found >= total_kw * 0.5  # At least half the keywords
    test_ok = test_kw_found >= total_kw * 0.5
    
    info_preserved = test_kw_found >= baseline_kw_found * 0.7  # 70%+ of baseline keyword coverage
    
    print(f"  Baseline answer ({t_baseline:.1f}s): {baseline_answer[:120]}")
    print(f"  Baseline keywords: {baseline_kw_found}/{total_kw}")
    print(f"  Compressed answer ({t_test:.1f}s): {test_answer[:120]}")
    print(f"  Compressed keywords: {test_kw_found}/{total_kw}")
    print(f"  Info preserved: {'✓' if info_preserved else '✗ LOSS'}")
    print()
    
    results.append({
        "task": label,
        "input_size": input_size,
        "output_size": output_size,
        "ratio_pct": round(ratio, 0),
        "compress_time_s": round(compress_time, 1),
        "baseline_keywords": f"{baseline_kw_found}/{total_kw}",
        "compressed_keywords": f"{test_kw_found}/{total_kw}",
        "info_preserved": info_preserved,
        "baseline_ok": baseline_ok,
        "test_ok": test_ok,
        "compressed_preview": compressed[:120],
    })

# ═══════════════════════════════════════════════════════
#  Summary table
# ═══════════════════════════════════════════════════════
print("=" * 72)
print("  GATE RESULTS")
print("=" * 72)

# Table header
print(f"  {'Task':<30} {'Input':>7} {'Compressed':>10} {'Ratio':>6} {'BL KW':>6} {'Comp KW':>7} {'OK?':>4}")
print(f"  {'-'*30} {'-'*7} {'-'*10} {'-'*6} {'-'*6} {'-'*7} {'-'*4}")

info_preserved_count = 0
ratios = []

for r in results:
    ok = "✓" if r["info_preserved"] else "✗"
    info_preserved_count += 1 if r["info_preserved"] else 0
    ratios.append(r["ratio_pct"])
    print(f"  {r['task']:<30} {r['input_size']:>7,} {r['output_size']:>10,} {r['ratio_pct']:>5.0f}% {r['baseline_keywords']:>6} {r['compressed_keywords']:>7} {ok:>4}")

print()
avg_ratio = sum(ratios) / len(ratios) if ratios else 0
min_ratio = min(ratios) if ratios else 0
max_ratio = max(ratios) if ratios else 0

print(f"  Average compression ratio: {avg_ratio:.0f}%")
print(f"  Range: {min_ratio:.0f}% – {max_ratio:.0f}%")
print(f"  Information preserved: {info_preserved_count}/{len(results)}")
print()

# ═══════════════════════════════════════════════════════
#  Find safe compression floor
# ═══════════════════════════════════════════════════════

# The safe floor is the lowest ratio where info was still preserved
safe_ratios = [r["ratio_pct"] for r in results if r["info_preserved"]]
unsafe_ratios = [r["ratio_pct"] for r in results if not r["info_preserved"]]

safe_floor = max(safe_ratios) if safe_ratios else 30  # Conservative default
# Actually: the safe floor is the highest ratio that STILL preserved info
# If info was lost at 15% but preserved at 25%, safe floor = 25%
# The floor means "don't go below this"

# More precisely: find the lowest ratio where info was still preserved
if safe_ratios:
    compression_floor = min(safe_ratios)
    # But if there's an unsafe ratio above the minimum safe, that's the real floor
    if unsafe_ratios:
        problem_ratio = max(unsafe_ratios)
        if problem_ratio > compression_floor:
            compression_floor = max(unsafe_ratios) + 5  # Add margin
else:
    compression_floor = 30

print(f"  Compression ratios where info was preserved: {sorted(safe_ratios)}")
if unsafe_ratios:
    print(f"  Compression ratios where info was LOST: {sorted(unsafe_ratios)}")

# The floor is: don't compress below X% — if a compression ratio goes below X, it's too aggressive
# We set the floor as the lowest safe ratio observed, plus 5pp margin
floor_pct = max(min(safe_ratios) + 5, 20) if safe_ratios else 25
print(f"  ** Safe compression floor: ≥{floor_pct:.0f}% of input **")
print(f"  (Compress no further than {floor_pct:.0f}% — below that, info loss risk)")
print()

# ═══════════════════════════════════════════════════════
#  Gate decision
# ═══════════════════════════════════════════════════════
gate_passed = info_preserved_count >= 4  # Info preserved in ≥4/5 tasks
print(f"  GATE: {'✅ PASS' if gate_passed else '❌ FAIL'}")
if gate_passed:
    print(f"  Context engineer preserves critical info in ≥4/5 tasks with {avg_ratio:.0f}% avg compression.")
    print(f"  Phase C (Orchestrator Loop) is unblocked.")
    print(f"  Pipeline safe floor: compress to no less than {floor_pct:.0f}% of input.")
else:
    print(f"  FAIL: Info preserved in only {info_preserved_count}/5 tasks. Tune system prompt.")
print()

sys.exit(0 if gate_passed else 1)
