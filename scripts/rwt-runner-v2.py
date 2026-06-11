#!/usr/bin/env python3.10
"""
RWT Runner v2 — Fixed prompt (WEB CONTEXT override) + Tavily extract for RWT-4.
Runs Tasks 1, 6, 4 only.

Changes from v1:
  1. WEB CONTEXT override: explicit instruction forcing model to use injected data
  2. tavily_extract(url): fetch actual page content for RWT-4
  3. Task 4 wired to real URL fetching
"""
import json, os, sys, time, re, ast, subprocess
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
RESULTS_DIR = "/tmp/maibs-self-improvement-framework/results/rwt-run-2"
REPO_DIR = "/tmp/maibs-self-improvement-framework"
EXPERIENCE_INDEX = f"{REPO_DIR}/experiences/EXPERIENCE_INDEX.md"

os.makedirs(RESULTS_DIR, exist_ok=True)

# ── WEB CONTEXT OVERRIDE INSTRUCTION ───────────────────
# This is the key fix: force the model to trust injected data over training data.
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

# ── Tavily search snippet ──────────────────────────────
def tavily_snippet(query: str, max_results=3) -> str:
    """Get WEB CONTEXT snippet from Tavily search. Returns '' on any error."""
    try:
        r = req.post(TAVILY_SEARCH_URL, json={
            "api_key": TAVILY_KEY, "query": query,
            "max_results": max_results, "search_depth": "basic"
        }, timeout=15)
        data = r.json()
        results = [x for x in data.get("results", []) if x.get("score", 0) > 0.7]
        if not results:
            return ""

        parts = ["## WEB CONTEXT (Tavily — live search results)"]
        for res in results[:3]:
            title = res.get("title", "")[:100]
            content = res.get("content", "")[:400]
            url = res.get("url", "")
            parts.append(f"\n### {title}")
            parts.append(content)
            if url:
                parts.append(f"Source: {url}")

        text = "\n".join(parts)
        if len(text) > 2400:
            text = text[:2400] + "\n[truncated]"
        return text
    except Exception:
        return ""

# ── NEW: Tavily extract (URL → page content) ───────────
def tavily_extract(url: str) -> str:
    """Fetch actual page content via Tavily extract API. Returns '' on any error."""
    try:
        r = req.post(TAVILY_EXTRACT_URL, json={
            "api_key": TAVILY_KEY,
            "urls": [url],
            "extract_depth": "basic",
            "include_images": False,
        }, timeout=30)
        data = r.json()

        results = data.get("results", [])
        if not results:
            # Try the "extracted_content" field (Tavily API v2 format)
            if "extracted_content" in data:
                return data["extracted_content"][:3000]
            return ""

        content = results[0].get("raw_content", "") or results[0].get("content", "")
        if not content:
            return ""

        # Cap at ~3000 chars
        if len(content) > 3000:
            content = content[:3000] + "\n[truncated]"

        title = results[0].get("title", "Page")
        url_out = results[0].get("url", url)

        return f"""## WEB CONTEXT — Page Extract (Tavily)

**Source:** {url_out}
**Title:** {title}

{content}"""

    except Exception as e:
        print(f"  [tavily_extract error: {e}]", flush=True)
        return ""

# ── LLM calls ──────────────────────────────────────────
def call_gemma(prompt: str, timeout=300) -> str:
    try:
        r = req.post(LLAMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800, "temperature": 0,
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

# ── Scoring functions (same as v1) ─────────────────────
def score_rwt1(output: str) -> tuple[int, str]:
    version_found = re.search(r'(?:requests\s*)?(?:version\s*)?(\d+\.\d+\.\d+)', output)
    version_str = version_found.group(1) if version_found else "none"
    version_ok = version_found and version_str >= "2.32"
    has_url = bool(re.search(r'https?://[^\s\)]+', output))
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    code_valid = False
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = True
        except: pass
    changes = len(re.findall(r'(?:^|\n)\s*(?:[-*•]|\d+\.)\s+\w', output))
    if version_ok and changes >= 2 and code_valid and has_url:
        return 100, f"Version {version_str}, {changes} changes, valid code, URL present"
    elif version_ok and (code_valid or has_url):
        return 50, f"Version {version_str} but missing some elements"
    else:
        return 0, f"Missing version/URL/code (found version: {version_str})"

def score_rwt6(output: str) -> tuple[int, str]:
    has_endpoint = "api.github.com/repos/" in output
    has_headers = "vnd.github" in output or "X-GitHub-Api-Version" in output or "application/vnd.github+json" in output
    has_rate = "X-RateLimit" in output or "status_code" in output or "403" in output
    has_correct_fields = "stargazers_count" in output and "open_issues" in output
    code_valid = False
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = "get_repo_info" in code_match.group(1)
        except: pass
    points = sum([has_endpoint, has_headers, has_rate, has_correct_fields, code_valid])
    if points >= 4:
        return 100, f"All {points}/5 checks passed"
    elif points >= 2:
        return 50, f"{points}/5 checks passed"
    else:
        return 0, f"Only {points}/5 checks passed"

def score_rwt4(output: str) -> tuple[int, str]:
    """RWT-4: Web extraction. Checks for evidence of actual page reading."""
    # Evidence of real extraction: specific method names from requests docs
    has_get = "GET" in output
    has_post = "POST" in output
    has_put = "PUT" in output
    methods_found = sum([has_get, has_post, has_put])

    has_url = bool(re.search(r'https?://[^\s\)]+', output))
    has_headers = len(re.findall(r'^#{1,3}\s', output, re.MULTILINE)) >= 2
    word_count = len(output.split())
    size_ok = 100 < word_count < 2000
    has_ssl = "ssl" in output.lower() or "SSL" in output or "verify" in output.lower()

    # More weight on actual content matching
    content_points = methods_found  # 0-3

    points = content_points + sum([has_url, has_headers, size_ok, has_ssl])
    if points >= 6 and methods_found >= 3:
        return 100, f"3 methods found, SSL:{has_ssl}, structured:{has_headers}, size:{word_count}w"
    elif points >= 4:
        return 50, f"{methods_found}/3 methods, SSL:{has_ssl}, structured:{has_headers}, size:{word_count}w"
    else:
        return 0, f"{methods_found}/3 methods, SSL:{has_ssl}, content evidence weak"

# ── Framework path (v2 — with WEB CONTEXT override) ────
def run_framework(task_id: str, task_desc: str, web_context: str = "",
                  exp_context: str = "") -> dict:
    """Run task through Gemma + framework with WEB CONTEXT override."""
    t0 = time.time()
    path_taken = []

    if web_context:
        path_taken.append("web_context")
    if exp_context:
        path_taken.append("experience_index")

    # Build prompt with OVERRIDE instruction
    prompt_parts = ["You are Gemma, a helpful coding assistant.\n"]

    # If we have web context, put the OVERRIDE instruction BEFORE the task
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

    # Call Gemma
    output = call_gemma(prompt, timeout=300)

    if "ERROR:" in output:
        clean_prompt = f"TASK: {task_desc}\n\nWrite the solution.\n"
        output = call_gemma(clean_prompt, timeout=300)

    elapsed = time.time() - t0

    return {
        "task_id": task_id,
        "model": "Gemma 4 E4B + framework (v2 override)",
        "output": output,
        "path_taken": path_taken,
        "elapsed": round(elapsed, 1),
        "web_context_used": bool(web_context),
        "experience_used": bool(exp_context),
    }

# ── Bare frontier path (unchanged) ─────────────────────
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
        "experience_used": False,
    }

# ── Tasks (1, 6, 4 only) ───────────────────────────────
def main():
    import sys
    sys.stdout.reconfigure(line_buffering=True)

    results = []

    # ═══════════════════════════════════════════════════
    # RWT-1: Live Docs Lookup
    # ═══════════════════════════════════════════════════
    task_1_desc = (
        "What changed in the Python requests library's latest release? "
        "Search the web to find the current version (requests 2.34.2 or newer). "
        "Summarize the key changes from the latest release notes, and show a working "
        "Python usage example for the newest feature. Include the source URL."
    )

    print(f"\n{'='*60}", flush=True)
    print("RWT-1: Live Docs Lookup", flush=True)
    print(f"{'='*60}", flush=True)

    # Get Tavily search results for RWT-1
    print("  [Tavily] Searching for requests release notes...", flush=True)
    web_ctx_1 = tavily_snippet("requests library latest release notes changelog pypi")
    print(f"  [Tavily] Got {'snippet' if web_ctx_1 else 'NOTHING'} ({len(web_ctx_1)} chars)", flush=True)

    print("  [Gemma+framework] Running...", flush=True)
    fw1 = run_framework("RWT-1", task_1_desc, web_context=web_ctx_1)
    fw1_score, fw1_note = score_rwt1(fw1["output"])
    fw1["score"] = fw1_score
    fw1["score_note"] = fw1_note
    print(f"  [Gemma+framework] Score: {fw1_score}/100 — {fw1_note}", flush=True)
    print(f"  [Gemma+framework] Time: {fw1['elapsed']}s, Path: {fw1['path_taken']}", flush=True)

    # Show what the model actually said about version
    ver_match = re.search(r'(\d+\.\d+\.\d+)', fw1["output"])
    print(f"  [Gemma] Version cited: {ver_match.group(1) if ver_match else 'NONE'}", flush=True)

    print("  [Frontier bare] Running...", flush=True)
    fr1 = run_frontier("RWT-1", task_1_desc)
    fr1_score, fr1_note = score_rwt1(fr1["output"])
    fr1["score"] = fr1_score
    fr1["score_note"] = fr1_note
    print(f"  [Frontier bare] Score: {fr1_score}/100 — {fr1_note}", flush=True)

    # Save RWT-1 outputs
    for prefix, res in [("fw", fw1), ("fr", fr1)]:
        outpath = f"{RESULTS_DIR}/RWT-1_{prefix}.txt"
        with open(outpath, "w") as f:
            f.write(f"Task: RWT-1 — Live Docs Lookup (v2)\n")
            f.write(f"Model: {res['model']}\n")
            f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
            f.write(f"Path: {res['path_taken']}\n")
            f.write(f"Elapsed: {res['elapsed']}s\n")
            f.write(f"Web context: {res['web_context_used']}\n")
            f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
            f.write(res['output'])

    results.append({
        "task_id": "RWT-1",
        "title": "Live Docs Lookup",
        "gemma_score": fw1_score, "gemma_note": fw1_note,
        "gemma_path": fw1["path_taken"], "gemma_time": fw1["elapsed"],
        "frontier_score": fr1_score, "frontier_note": fr1_note,
        "frontier_time": fr1["elapsed"],
    })

    time.sleep(2)

    # ═══════════════════════════════════════════════════
    # RWT-6: Current API Coding
    # ═══════════════════════════════════════════════════
    task_6_desc = (
        "Write a Python function get_repo_info(owner: str, repo: str) -> dict "
        "that calls the GitHub REST API to get repository information. "
        "Search the web for the current GitHub API v3 REST endpoint format and required headers. "
        "The function should: (1) Use the correct current API endpoint, "
        "(2) Include proper headers like Accept: application/vnd.github+json, "
        "(3) Handle rate limiting by checking for 403 status and X-RateLimit-Remaining header, "
        "(4) Return a dict with: name, stars (stargazers_count), language, open_issues."
    )

    print(f"\n{'='*60}", flush=True)
    print("RWT-6: Current API Coding", flush=True)
    print(f"{'='*60}", flush=True)

    print("  [Tavily] Searching for GitHub API current headers...", flush=True)
    web_ctx_6 = tavily_snippet("GitHub REST API v3 current headers endpoint repos stargazers_count 2024 2025")
    print(f"  [Tavily] Got {'snippet' if web_ctx_6 else 'NOTHING'} ({len(web_ctx_6)} chars)", flush=True)

    print("  [Gemma+framework] Running...", flush=True)
    fw6 = run_framework("RWT-6", task_6_desc, web_context=web_ctx_6)
    fw6_score, fw6_note = score_rwt6(fw6["output"])
    fw6["score"] = fw6_score
    fw6["score_note"] = fw6_note
    print(f"  [Gemma+framework] Score: {fw6_score}/100 — {fw6_note}", flush=True)
    print(f"  [Gemma+framework] Time: {fw6['elapsed']}s, Path: {fw6['path_taken']}", flush=True)

    # Show key API details
    for check in ["api.github.com/repos/", "vnd.github", "X-RateLimit", "stargazers_count"]:
        found = check in fw6["output"]
        print(f"  [Gemma] '{check}' in output: {found}", flush=True)

    print("  [Frontier bare] Running...", flush=True)
    fr6 = run_frontier("RWT-6", task_6_desc)
    fr6_score, fr6_note = score_rwt6(fr6["output"])
    fr6["score"] = fr6_score
    fr6["score_note"] = fr6_note
    print(f"  [Frontier bare] Score: {fr6_score}/100 — {fr6_note}", flush=True)

    for prefix, res in [("fw", fw6), ("fr", fr6)]:
        outpath = f"{RESULTS_DIR}/RWT-6_{prefix}.txt"
        with open(outpath, "w") as f:
            f.write(f"Task: RWT-6 — Current API Coding (v2)\n")
            f.write(f"Model: {res['model']}\n")
            f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
            f.write(f"Path: {res['path_taken']}\n")
            f.write(f"Elapsed: {res['elapsed']}s\n")
            f.write(f"Web context: {res['web_context_used']}\n")
            f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
            f.write(res['output'])

    results.append({
        "task_id": "RWT-6",
        "title": "Current API Coding",
        "gemma_score": fw6_score, "gemma_note": fw6_note,
        "gemma_path": fw6["path_taken"], "gemma_time": fw6["elapsed"],
        "frontier_score": fr6_score, "frontier_note": fr6_note,
        "frontier_time": fr6["elapsed"],
    })

    time.sleep(2)

    # ═══════════════════════════════════════════════════
    # RWT-4: Web Extraction (FIXED — Tavily extract URL)
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
    print("RWT-4: Web Extraction (Tavily extract)", flush=True)
    print(f"{'='*60}", flush=True)

    # NEW: Use Tavily extract to fetch the actual page
    target_url = "https://docs.python-requests.org/en/latest/user/quickstart/"
    print(f"  [Tavily extract] Fetching {target_url}...", flush=True)
    web_ctx_4 = tavily_extract(target_url)
    print(f"  [Tavily extract] Got {'content' if web_ctx_4 else 'NOTHING'} ({len(web_ctx_4)} chars)", flush=True)

    # Fallback: if extract fails, try search
    if not web_ctx_4:
        print("  [Tavily extract] Failed, falling back to search...", flush=True)
        web_ctx_4 = tavily_snippet("python requests library quickstart documentation GET POST PUT SSL")
        print(f"  [Tavily search] Got {'snippet' if web_ctx_4 else 'NOTHING'} ({len(web_ctx_4)} chars)", flush=True)

    print("  [Gemma+framework] Running...", flush=True)
    fw4 = run_framework("RWT-4", task_4_desc, web_context=web_ctx_4)
    fw4_score, fw4_note = score_rwt4(fw4["output"])
    fw4["score"] = fw4_score
    fw4["score_note"] = fw4_note
    print(f"  [Gemma+framework] Score: {fw4_score}/100 — {fw4_note}", flush=True)
    print(f"  [Gemma+framework] Time: {fw4['elapsed']}s, Path: {fw4['path_taken']}", flush=True)

    # Check for real content evidence
    for method in ["GET", "POST", "PUT"]:
        found = method in fw4["output"]
        print(f"  [Gemma] '{method}' in output: {found}", flush=True)
    print(f"  [Gemma] SSL mention: {'SSL' in fw4['output'] or 'ssl' in fw4['output'].lower()}", flush=True)

    print("  [Frontier bare] Running...", flush=True)
    fr4 = run_frontier("RWT-4", task_4_desc)
    fr4_score, fr4_note = score_rwt4(fr4["output"])
    fr4["score"] = fr4_score
    fr4["score_note"] = fr4_note
    print(f"  [Frontier bare] Score: {fr4_score}/100 — {fr4_note}", flush=True)

    for prefix, res in [("fw", fw4), ("fr", fr4)]:
        outpath = f"{RESULTS_DIR}/RWT-4_{prefix}.txt"
        with open(outpath, "w") as f:
            f.write(f"Task: RWT-4 — Web Extraction (v2 — Tavily extract)\n")
            f.write(f"Model: {res['model']}\n")
            f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
            f.write(f"Path: {res['path_taken']}\n")
            f.write(f"Elapsed: {res['elapsed']}s\n")
            f.write(f"Web context: {res['web_context_used']}\n")
            f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
            f.write(res['output'])

    results.append({
        "task_id": "RWT-4",
        "title": "Web Extraction",
        "gemma_score": fw4_score, "gemma_note": fw4_note,
        "gemma_path": fw4["path_taken"], "gemma_time": fw4["elapsed"],
        "frontier_score": fr4_score, "frontier_note": fr4_note,
        "frontier_time": fr4["elapsed"],
    })

    # ── Summary ────────────────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print("RWT RUN 2 — RESULTS", flush=True)
    print(f"{'='*60}", flush=True)

    for r in results:
        print(f"\n  {r['task_id']} {r['title']}:", flush=True)
        print(f"    Gemma+fw (v2): {r['gemma_score']}/100 — {r['gemma_note']}", flush=True)
        print(f"    Frontier:      {r['frontier_score']}/100 — {r['frontier_note']}", flush=True)
        print(f"    Gemma path: {r['gemma_path']}", flush=True)

    # Save summary JSON
    summary_path = f"{RESULTS_DIR}/summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results: {RESULTS_DIR}/", flush=True)
    print(f"Summary: {summary_path}", flush=True)

    return results

if __name__ == "__main__":
    main()
