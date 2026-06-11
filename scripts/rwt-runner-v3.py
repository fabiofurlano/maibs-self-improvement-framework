#!/usr/bin/env python3.10
"""
RWT Runner v3 — Three fixes from Run 2:
  1. Tavily dual-query, score >= 0.5, 800-char cap
  2. RWT-6 replaced: Anthropic Messages API (claude-sonnet-4-20250514 — post Gemma cutoff)
  3. RWT-4 page extract capped at 800 chars
"""
import json, os, sys, time, re, ast
import requests as req

# ── Config ────────────────────────────────────────────
TAVILY_KEY = "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"
OPENROUTER_KEY = "OPENROUTER_KEY_PLACEHOLDER"
LLAMA_URL = "http://localhost:8080/v1/chat/completions"
LLAMA_MODEL = "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
FRONTIER_MODEL = "deepseek/deepseek-chat"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
RESULTS_DIR = "/tmp/maibs-self-improvement-framework/results/rwt-run-3"
REPO_DIR = "/tmp/maibs-self-improvement-framework"

os.makedirs(RESULTS_DIR, exist_ok=True)

# ── WEB CONTEXT OVERRIDE (kept from v2 — works) ───────
WEB_OVERRIDE = """
!!! CRITICAL INSTRUCTION — READ THIS FIRST !!!

The ## WEB CONTEXT block below contains CURRENT, VERIFIED information retrieved
from live web searches performed RIGHT NOW. This data is authoritative.

YOU MUST use the information in the WEB CONTEXT block. Do NOT rely on your
training data for anything covered in the WEB CONTEXT. If the WEB CONTEXT says
X, the answer is X — even if your training data says something different.

Your training cutoff is early 2025. The WEB CONTEXT is from TODAY (June 2026).
The web data is CORRECT. Your training data is STALE.

If you ignore the WEB CONTEXT and use training data instead, your answer will
be WRONG and will receive a score of ZERO.
"""

# ── FIX 1: Tavily — dual query, score >= 0.5, 800-char cap ──
def tavily_search_single(query: str, score_threshold=0.5, max_results=5) -> list:
    """Run a single Tavily search, return filtered results."""
    try:
        r = req.post(TAVILY_SEARCH_URL, json={
            "api_key": TAVILY_KEY, "query": query,
            "max_results": max_results, "search_depth": "basic"
        }, timeout=15)
        data = r.json()
        return [x for x in data.get("results", []) if x.get("score", 0) >= score_threshold]
    except Exception:
        return []

def tavily_multi_search(queries: list[str], score_threshold=0.5) -> str:
    """Run multiple queries, merge best results, cap at 800 chars."""
    all_results = []
    for q in queries:
        results = tavily_search_single(q, score_threshold)
        all_results.extend(results)

    if not all_results:
        return ""

    # Deduplicate by URL
    seen = set()
    unique = []
    for r in all_results:
        url = r.get("url", "")
        if url not in seen:
            seen.add(url)
            unique.append(r)
        if len(unique) >= 3:
            break

    # Build snippet
    parts = ["## WEB CONTEXT (Tavily — live search)"]
    for res in unique[:3]:
        title = res.get("title", "")[:100]
        content = res.get("content", "")[:300]
        url = res.get("url", "")
        parts.append(f"\n**{title}**")
        parts.append(content)
        if url:
            parts.append(f"Source: {url}")

    text = "\n".join(parts)
    # FIX: hard 800-char cap
    if len(text) > 800:
        text = text[:800] + "\n[truncated]"
    return text

# ── FIX 3: Tavily extract — 800-char cap ───────────────
def tavily_extract(url: str) -> str:
    """Fetch page content via Tavily extract, capped at 800 chars."""
    try:
        r = req.post(TAVILY_EXTRACT_URL, json={
            "api_key": TAVILY_KEY,
            "urls": [url],
            "extract_depth": "basic",
            "include_images": False,
        }, timeout=30)
        data = r.json()

        results = data.get("results", [])
        content = ""
        if results:
            content = results[0].get("raw_content", "") or results[0].get("content", "")
        elif "extracted_content" in data:
            content = data["extracted_content"]

        if not content:
            return ""

        # FIX: hard cap at 800 chars
        if len(content) > 800:
            content = content[:800] + "\n[truncated]"

        title = results[0].get("title", "Page") if results else "Page"
        url_out = results[0].get("url", url) if results else url

        return f"""## WEB CONTEXT — Page Extract (Tavily)

**Source:** {url_out}

{content}"""

    except Exception as e:
        print(f"  [tavily_extract error: {e}]", flush=True)
        return ""

# ── LLM calls ──────────────────────────────────────────
def call_gemma(prompt: str, timeout=300) -> str:
    try:
        r = req.post(LLAMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1200, "temperature": 0,
        }, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"

def call_frontier(prompt: str, timeout=120) -> str:
    try:
        r = req.post(OR_URL, json={
            "model": FRONTIER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800, "temperature": 0,
        }, headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json"
        }, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"

# ── Scoring ────────────────────────────────────────────
def score_rwt1(output: str) -> tuple[int, str]:
    """RWT-1: Live docs lookup — honest scoring."""
    version_found = re.search(r'(\d+\.\d+\.\d+)', output)
    version_str = version_found.group(1) if version_found else "none"

    # Check if version came from training data (2.31.0 or 2.28.0 = stale)
    is_stale_version = version_str in ("2.31.0", "2.28.0", "2.32.0")
    is_current = version_str >= "2.34"

    has_url = bool(re.search(r'https?://[^\s\)]+', output))
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    code_valid = False
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = True
        except: pass

    # Count real bullet points (evidence of detailed response)
    changes = len(re.findall(r'(?:^|\n)\s*(?:[-*•]|\d+\.)\s+\w', output))

    # Did the model explicitly cite the web context?
    cites_web = "web context" in output.lower() or "tavily" in output.lower()

    if is_current and code_valid and has_url and changes >= 1:
        return 100, f"Current version {version_str}, {changes} changes, code+URL present"
    elif is_current and not is_stale_version:
        return 50, f"Correct version {version_str} but incomplete (changes:{changes}, url:{has_url}, code:{code_valid})"
    elif is_stale_version:
        return 0, f"Stale version {version_str} — from training data, not web"
    else:
        return 0, f"No usable version found (got: {version_str})"

def score_rwt4(output: str) -> tuple[int, str]:
    """RWT-4: Web extraction."""
    has_get = "GET" in output
    has_post = "POST" in output
    has_put = "PUT" in output
    methods_found = sum([has_get, has_post, has_put])

    has_url = bool(re.search(r'https?://[^\s\)]+', output))
    has_headers = len(re.findall(r'^#{1,3}\s', output, re.MULTILINE)) >= 1
    word_count = len(output.split())
    size_ok = 50 < word_count < 2000
    has_ssl = "ssl" in output.lower() or "SSL" in output or "verify" in output.lower()
    not_garbage = output[:20] != "successsuccesssucce"  # detect Run 2 garbage

    if not not_garbage:
        return 0, "Garbage output (context overflow)"

    points = methods_found + sum([has_url, has_headers, size_ok, has_ssl, not_garbage])
    if points >= 6 and methods_found >= 2:
        return 100, f"{methods_found}/3 methods, SSL:{has_ssl}, structured:{has_headers}, size:{word_count}w"
    elif points >= 4:
        return 50, f"{methods_found}/3 methods, SSL:{has_ssl}, structured:{has_headers}, size:{word_count}w"
    else:
        return 0, f"{methods_found}/3 methods, content evidence weak"

# ── FIX 2: New RWT-6 scorer (Anthropic API) ────────────
def score_rwt6(output: str) -> tuple[int, str]:
    """RWT-6: Anthropic Messages API coding."""
    # Must use the correct model name (post-Gemma cutoff)
    has_correct_model = "claude-sonnet-4-20250514" in output

    # Must use correct endpoint
    has_endpoint = "api.anthropic.com" in output or "messages" in output

    # Must include anthropic-version header
    has_version_header = "anthropic-version" in output and ("2023-06-01" in output or "2023-01-01" in output)

    # Must include x-api-key
    has_api_key = "x-api-key" in output

    # Valid code
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    code_valid = False
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = "call_claude" in code_match.group(1) or "def " in code_match.group(1)
        except: pass

    # Critical: correct model name is the whole point of this test
    if not has_correct_model:
        # Check if they used a wrong/Hallucinated model name
        wrong_model = re.search(r'claude-\d[^\s"]*', output)
        if wrong_model:
            return 0, f"Wrong model: {wrong_model.group()} — expected claude-sonnet-4-20250514 (need Tavily)"
        return 0, "Missing correct model name (claude-sonnet-4-20250514)"

    points = sum([has_correct_model, has_endpoint, has_version_header, has_api_key, code_valid])
    if points >= 4:
        return 100, f"Correct model + {points}/5 checks"
    elif points >= 2:
        return 50, f"{points}/5 checks"
    else:
        return 0, f"Only {points}/5 checks"

# ── Framework path ─────────────────────────────────────
def run_framework(task_id: str, task_desc: str, web_context: str = "",
                  exp_context: str = "") -> dict:
    t0 = time.time()
    path_taken = []

    if web_context:
        path_taken.append("web_context")
    if exp_context:
        path_taken.append("experience_index")

    prompt_parts = ["You are Gemma, a helpful coding assistant.\n"]

    if web_context:
        prompt_parts.append(WEB_OVERRIDE)
        prompt_parts.append("\n")

    prompt_parts.append(f"TASK: {task_desc}\n")

    if web_context:
        prompt_parts.append(web_context)

    if exp_context:
        prompt_parts.append(exp_context)

    prompt_parts.append("\nWrite the solution. Include a Python code block if the task requires code.\n")

    prompt = "\n".join(prompt_parts)

    output = call_gemma(prompt, timeout=300)

    if "ERROR:" in output:
        clean_prompt = f"TASK: {task_desc}\n\nWrite the solution.\n"
        output = call_gemma(clean_prompt, timeout=300)

    elapsed = time.time() - t0

    return {
        "task_id": task_id,
        "model": "Gemma 4 E4B + framework (v3)",
        "output": output,
        "path_taken": path_taken,
        "elapsed": round(elapsed, 1),
        "web_context_used": bool(web_context),
    }

def run_frontier(task_id: str, task_desc: str) -> dict:
    t0 = time.time()
    prompt = f"TASK: {task_desc}\n\nWrite the solution.\n"
    output = call_frontier(prompt, timeout=120)
    elapsed = time.time() - t0
    return {
        "task_id": task_id,
        "model": f"Bare {FRONTIER_MODEL} (no tools)",
        "output": output,
        "path_taken": [],
        "elapsed": round(elapsed, 1),
        "web_context_used": False,
    }

# ── Main ───────────────────────────────────────────────
def main():
    sys.stdout.reconfigure(line_buffering=True)

    results = []

    # ═══════════════════════════════════════════════════
    # RWT-1: Live Docs Lookup (dual-query Tavily)
    # ═══════════════════════════════════════════════════
    task_1_desc = (
        "What changed in the Python requests library's latest release? "
        "Identify the current version number. Summarize the key changes "
        "from the release notes, and show a working Python usage example "
        "for a feature from that release. Include the source URL."
    )

    print(f"\n{'='*60}", flush=True)
    print("RWT-1: Live Docs Lookup", flush=True)
    print(f"{'='*60}", flush=True)

    print("  [Tavily] Dual query: 'requests changelog' + 'requests release notes'...", flush=True)
    web_ctx_1 = tavily_multi_search([
        "requests library 2.34 changelog",
        "python requests latest release notes 2025"
    ], score_threshold=0.5)
    print(f"  [Tavily] Got {'snippet' if web_ctx_1 else 'NOTHING'} ({len(web_ctx_1)} chars)", flush=True)

    print("  [Gemma+framework] Running...", flush=True)
    fw1 = run_framework("RWT-1", task_1_desc, web_context=web_ctx_1)
    fw1_score, fw1_note = score_rwt1(fw1["output"])
    fw1["score"] = fw1_score
    fw1["score_note"] = fw1_note
    ver_match = re.search(r'(\d+\.\d+\.\d+)', fw1["output"])
    print(f"  [Gemma] Version: {ver_match.group(1) if ver_match else 'NONE'} | Score: {fw1_score}/100 — {fw1_note}", flush=True)
    print(f"  [Gemma] Time: {fw1['elapsed']}s, Path: {fw1['path_taken']}", flush=True)

    print("  [Frontier bare] Running...", flush=True)
    fr1 = run_frontier("RWT-1", task_1_desc)
    fr1_score, fr1_note = score_rwt1(fr1["output"])
    fr1["score"] = fr1_score
    fr1["score_note"] = fr1_note
    ver_match_fr = re.search(r'(\d+\.\d+\.\d+)', fr1["output"])
    print(f"  [Frontier] Version: {ver_match_fr.group(1) if ver_match_fr else 'NONE'} | Score: {fr1_score}/100 — {fr1_note}", flush=True)

    for prefix, res in [("fw", fw1), ("fr", fr1)]:
        outpath = f"{RESULTS_DIR}/RWT-1_{prefix}.txt"
        with open(outpath, "w") as f:
            f.write(f"Task: RWT-1 — Live Docs Lookup (v3)\n")
            f.write(f"Model: {res['model']}\n")
            f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
            f.write(f"Path: {res['path_taken']}\n")
            f.write(f"Elapsed: {res['elapsed']}s\n")
            f.write(f"Web context: {res['web_context_used']}\n")
            f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
            f.write(res['output'])

    results.append({
        "task_id": "RWT-1", "title": "Live Docs Lookup",
        "gemma_score": fw1_score, "gemma_note": fw1_note,
        "gemma_path": fw1["path_taken"], "gemma_time": fw1["elapsed"],
        "frontier_score": fr1_score, "frontier_note": fr1_note,
        "frontier_time": fr1["elapsed"],
    })

    time.sleep(2)

    # ═══════════════════════════════════════════════════
    # RWT-6: NEW — Anthropic Messages API (post-cutoff model)
    # ═══════════════════════════════════════════════════
    task_6_desc = (
        "Write a Python function call_claude(prompt: str) -> str that calls the "
        "Anthropic Messages API using the claude-sonnet-4-20250514 model. "
        "Include: (1) the correct API endpoint, (2) proper headers including "
        "x-api-key and anthropic-version: 2023-06-01, (3) the correct model name "
        "(claude-sonnet-4-20250514), (4) error handling for API errors. "
        "Return the text content from the response."
    )

    print(f"\n{'='*60}", flush=True)
    print("RWT-6: Anthropic Messages API (NEW — post-cutoff model name)", flush=True)
    print(f"{'='*60}", flush=True)

    print("  [Tavily] Searching for Anthropic API model name...", flush=True)
    web_ctx_6 = tavily_multi_search([
        "Anthropic Messages API claude-sonnet-4-20250514 endpoint",
        "anthropic python sdk messages create model name 2025"
    ], score_threshold=0.5)
    print(f"  [Tavily] Got {'snippet' if web_ctx_6 else 'NOTHING'} ({len(web_ctx_6)} chars)", flush=True)

    print("  [Gemma+framework] Running...", flush=True)
    fw6 = run_framework("RWT-6", task_6_desc, web_context=web_ctx_6)
    fw6_score, fw6_note = score_rwt6(fw6["output"])
    fw6["score"] = fw6_score
    fw6["score_note"] = fw6_note
    print(f"  [Gemma] Score: {fw6_score}/100 — {fw6_note}", flush=True)
    print(f"  [Gemma] Time: {fw6['elapsed']}s, Path: {fw6['path_taken']}", flush=True)
    # Quick evidence checks
    for check in ["claude-sonnet-4-20250514", "api.anthropic.com", "anthropic-version", "x-api-key"]:
        found = check in fw6["output"]
        print(f"  [Gemma] '{check}': {'YES' if found else 'NO'}", flush=True)

    print("  [Frontier bare] Running...", flush=True)
    fr6 = run_frontier("RWT-6", task_6_desc)
    fr6_score, fr6_note = score_rwt6(fr6["output"])
    fr6["score"] = fr6_score
    fr6["score_note"] = fr6_note
    print(f"  [Frontier] Score: {fr6_score}/100 — {fr6_note}", flush=True)
    for check in ["claude-sonnet-4-20250514", "api.anthropic.com"]:
        found = check in fr6["output"]
        print(f"  [Frontier] '{check}': {'YES' if found else 'NO'}", flush=True)

    for prefix, res in [("fw", fw6), ("fr", fr6)]:
        outpath = f"{RESULTS_DIR}/RWT-6_{prefix}.txt"
        with open(outpath, "w") as f:
            f.write(f"Task: RWT-6 — Anthropic Messages API (v3)\n")
            f.write(f"Model: {res['model']}\n")
            f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
            f.write(f"Path: {res['path_taken']}\n")
            f.write(f"Elapsed: {res['elapsed']}s\n")
            f.write(f"Web context: {res['web_context_used']}\n")
            f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
            f.write(res['output'])

    results.append({
        "task_id": "RWT-6", "title": "Anthropic API (new)",
        "gemma_score": fw6_score, "gemma_note": fw6_note,
        "gemma_path": fw6["path_taken"], "gemma_time": fw6["elapsed"],
        "frontier_score": fr6_score, "frontier_note": fr6_note,
        "frontier_time": fr6["elapsed"],
    })

    time.sleep(2)

    # ═══════════════════════════════════════════════════
    # RWT-4: Web Extraction (800-char cap)
    # ═══════════════════════════════════════════════════
    task_4_desc = (
        "Read the Python requests library documentation at "
        "https://docs.python-requests.org/en/latest/user/quickstart/ and extract: "
        "(1) The 3 most common HTTP methods shown, "
        "(2) One example for each method, "
        "(3) Any warning or note about SSL verification. "
        "Save as a structured summary with clear sections."
    )

    print(f"\n{'='*60}", flush=True)
    print("RWT-4: Web Extraction (800-char cap)", flush=True)
    print(f"{'='*60}", flush=True)

    target_url = "https://docs.python-requests.org/en/latest/user/quickstart/"
    print(f"  [Tavily extract] Fetching {target_url} (800-char cap)...", flush=True)
    web_ctx_4 = tavily_extract(target_url)
    print(f"  [Tavily extract] Got {'content' if web_ctx_4 else 'NOTHING'} ({len(web_ctx_4)} chars)", flush=True)

    if not web_ctx_4:
        print("  [Tavily extract] Failed, falling back to search...", flush=True)
        web_ctx_4 = tavily_multi_search([
            "python requests library quickstart documentation GET POST",
            "requests library HTTP methods SSL verify"
        ], score_threshold=0.5)
        print(f"  [Tavily search] Got {'snippet' if web_ctx_4 else 'NOTHING'} ({len(web_ctx_4)} chars)", flush=True)

    print("  [Gemma+framework] Running...", flush=True)
    fw4 = run_framework("RWT-4", task_4_desc, web_context=web_ctx_4)
    fw4_score, fw4_note = score_rwt4(fw4["output"])
    fw4["score"] = fw4_score
    fw4["score_note"] = fw4_note
    print(f"  [Gemma] Score: {fw4_score}/100 — {fw4_note}", flush=True)
    print(f"  [Gemma] Time: {fw4['elapsed']}s, Path: {fw4['path_taken']}", flush=True)
    for method in ["GET", "POST", "PUT"]:
        found = method in fw4["output"]
        print(f"  [Gemma] '{method}': {'YES' if found else 'NO'}", flush=True)
    print(f"  [Gemma] SSL: {'YES' if 'SSL' in fw4['output'] or 'ssl' in fw4['output'].lower() else 'NO'}", flush=True)
    not_garbage = fw4["output"][:20] != "successsuccesssucce"
    print(f"  [Gemma] Not garbage: {not_garbage}", flush=True)

    print("  [Frontier bare] Running...", flush=True)
    fr4 = run_frontier("RWT-4", task_4_desc)
    fr4_score, fr4_note = score_rwt4(fr4["output"])
    fr4["score"] = fr4_score
    fr4["score_note"] = fr4_note
    print(f"  [Frontier] Score: {fr4_score}/100 — {fr4_note}", flush=True)

    for prefix, res in [("fw", fw4), ("fr", fr4)]:
        outpath = f"{RESULTS_DIR}/RWT-4_{prefix}.txt"
        with open(outpath, "w") as f:
            f.write(f"Task: RWT-4 — Web Extraction (v3, 800-char cap)\n")
            f.write(f"Model: {res['model']}\n")
            f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
            f.write(f"Path: {res['path_taken']}\n")
            f.write(f"Elapsed: {res['elapsed']}s\n")
            f.write(f"Web context: {res['web_context_used']}\n")
            f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
            f.write(res['output'])

    results.append({
        "task_id": "RWT-4", "title": "Web Extraction",
        "gemma_score": fw4_score, "gemma_note": fw4_note,
        "gemma_path": fw4["path_taken"], "gemma_time": fw4["elapsed"],
        "frontier_score": fr4_score, "frontier_note": fr4_note,
        "frontier_time": fr4["elapsed"],
    })

    # ── Summary ────────────────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print("RWT RUN 3 — RESULTS", flush=True)
    print(f"{'='*60}", flush=True)

    for r in results:
        print(f"\n  {r['task_id']} {r['title']}:", flush=True)
        print(f"    Gemma+fw (v3): {r['gemma_score']}/100 — {r['gemma_note']}", flush=True)
        print(f"    Frontier:      {r['frontier_score']}/100 — {r['frontier_note']}", flush=True)
        print(f"    Gemma path: {r['gemma_path']}", flush=True)

    summary_path = f"{RESULTS_DIR}/summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results: {RESULTS_DIR}/", flush=True)

    return results

if __name__ == "__main__":
    main()
