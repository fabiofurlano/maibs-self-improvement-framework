#!/usr/bin/env python3.10
"""
RWT Runner — runs all 7 Real-World Tasks through:
  A) Gemma 4 E4B + full framework (Tavily, memory, lifeline)
  B) Bare frontier model (DeepSeek V4 Pro via OpenRouter, no tools)

Scores per rubrics in projects/maibs/rwt-rubrics/
"""
import json, os, sys, time, re, ast, subprocess
import requests as req

# ── Config ────────────────────────────────────────────
TAVILY_KEY = "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"
OPENROUTER_KEY = "OPENROUTER_KEY_PLACEHOLDER"
LLAMA_URL = "http://localhost:8080/v1/chat/completions"
LLAMA_MODEL = "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
FRONTIER_MODEL = "deepseek/deepseek-chat"  # DeepSeek V3.1 (non-reasoning)
TAVILY_URL = "https://api.tavily.com/search"
RESULTS_DIR = "/tmp/maibs-self-improvement-framework/results/rwt-run-1"
REPO_DIR = "/tmp/maibs-self-improvement-framework"
EXPERIENCE_INDEX = f"{REPO_DIR}/experiences/EXPERIENCE_INDEX.md"
EXPERIENCES_DIR = f"{REPO_DIR}/experiences/coding"

os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Tavily snippet (same as before, 600-token cap) ────
def tavily_snippet(query: str, max_results=3) -> str:
    """Get WEB CONTEXT snippet from Tavily. Returns '' on any error."""
    try:
        r = req.post(TAVILY_URL, json={
            "api_key": TAVILY_KEY, "query": query,
            "max_results": max_results, "search_depth": "basic"
        }, timeout=15)
        data = r.json()
        results = [x for x in data.get("results", []) if x.get("score", 0) > 0.7]
        if not results:
            return ""
        
        # Build compact snippet
        parts = ["## WEB CONTEXT (Tavily)"]
        for res in results[:3]:
            title = res.get("title", "")[:100]
            content = res.get("content", "")[:400]
            url = res.get("url", "")
            parts.append(f"\n### {title}")
            parts.append(content)
            if url:
                parts.append(f"Source: {url}")
        
        text = "\n".join(parts)
        # 600-token cap (rough: 4 chars/token)
        if len(text) > 2400:
            text = text[:2400] + "\n[truncated]"
        return text
    except Exception:
        return ""

# ── LLM calls ──────────────────────────────────────────
def call_gemma(prompt: str, timeout=300) -> str:
    """Call local Gemma 4 E4B."""
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
    """Call bare frontier model via OpenRouter — NO tools."""
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

# ── Scoring functions (per rubric) ─────────────────────
def score_rwt1(output: str) -> tuple[int, str]:
    """RWT-1: Live docs lookup."""
    # Check for version
    version_found = re.search(r'2\.\d+\.\d+', output)
    version_ok = version_found and version_found.group() >= "2.32"
    
    # Check for source URL
    has_url = bool(re.search(r'https?://[^\s]+', output))
    
    # Check for code example (valid Python)
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    code_valid = False
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = True
        except: pass
    
    # Count real changes cited (heuristic: bullet points or numbered items)
    changes = len(re.findall(r'(?:^|\n)\s*(?:[-*•]|\d+\.)\s+\w', output))
    
    if version_ok and changes >= 2 and code_valid and has_url:
        return 100, f"Version {version_found.group()}, {changes} changes, valid code, URL present"
    elif version_ok and (code_valid or has_url):
        return 50, f"Version {version_found.group()} but missing some elements"
    else:
        return 0, "Missing version, URL, or code"

def score_rwt2(output: str, path_taken: list = None) -> tuple[int, str]:
    """RWT-2: Memory carry-over. Checks for experience hit."""
    # Check for experience_index in path
    has_experience = path_taken and "experience_index" in path_taken if path_taken else "experience_index" in output.lower()
    
    # Check for correct extract_domain
    has_domain_extraction = "extract_domain" in output
    has_correct_split = "@" in output and ("split" in output.lower() or "partition" in output.lower() or "index" in output.lower())
    
    # Check test cases
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    code_valid = False
    if code_match:
        try:
            code = code_match.group(1)
            ast.parse(code)
            code_valid = "extract_domain" in code and "@" in code
        except: pass
    
    if has_experience and code_valid and has_correct_split:
        return 100, "Experience hit, correct extract_domain function"
    elif code_valid and not has_experience:
        return 50, "Correct solution but no experience usage (cold solve)"
    else:
        return 0, "No experience usage, incorrect solution"

def score_rwt5(output: str, path_taken: list = None) -> tuple[int, str]:
    """RWT-5: Bug-fix with history."""
    has_experience = path_taken and "experience_index" in path_taken if path_taken else "experience_index" in output.lower()
    
    # Check for correct inclusive slicing
    has_inclusive = "end+1" in output or "end + 1" in output
    
    # Check test cases
    tests_ok = all(x in output for x in ["[4, 5, 6]", "[2]", "[]"]) or \
               all(x in output for x in ["[4,5,6]", "[2]", "[]"])
    
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    code_valid = False
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = "get_middle_third" in code_match.group(1)
        except: pass
    
    if has_experience and code_valid and has_inclusive:
        return 100, "Experience hit, correct inclusive slicing"
    elif code_valid and not has_experience:
        return 50, "Correct solution but no experience usage (cold solve)"
    else:
        return 0, "No experience usage, incorrect slicing"

def score_rwt6(output: str) -> tuple[int, str]:
    """RWT-6: Current API coding."""
    # Check for correct endpoint
    has_endpoint = "api.github.com/repos/" in output
    
    # Check for current headers
    has_headers = "vnd.github" in output or "X-GitHub-Api-Version" in output or "application/vnd.github+json" in output
    
    # Check for rate limit
    has_rate = "X-RateLimit" in output or "status_code" in output or "403" in output
    
    # Check correct field names
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

def score_rwt7(output: str) -> tuple[int, str]:
    """RWT-7: Multi-step orchestration."""
    # Check all 4 functions present
    funcs = ["fetch_user_data", "filter_adults", "extract_emails", "main"]
    funcs_found = sum(1 for f in funcs if f"def {f}" in output)
    
    # Check chaining in main
    has_chaining = all(f in output for f in funcs[:3]) and "main" in output
    
    # Check logic
    has_age_filter = ">= 18" in output or "> 17" in output
    has_email_extract = '"email"' in output or "'email'" in output
    
    # Check mixed ages
    has_under_18 = "16" in output or "17" in output or "15" in output or "14" in output
    
    code_valid = False
    code_match = re.search(r'```python\s*\n(.*?)```', output, re.DOTALL)
    if code_match:
        try:
            ast.parse(code_match.group(1))
            code_valid = True
        except: pass
    
    points = funcs_found + sum([has_chaining, has_age_filter, has_email_extract, has_under_18, code_valid])
    if points >= 7 and funcs_found >= 4:
        return 100, f"All 4 functions, correct chaining, {points}/9 checks"
    elif points >= 4 and funcs_found >= 3:
        return 50, f"{funcs_found}/4 functions, {points}/9 checks"
    else:
        return 0, f"Only {funcs_found}/4 functions, {points}/9 checks"

def score_rwt3(output: str) -> tuple[int, str]:
    """RWT-3: Wiki authoring."""
    # Check YAML frontmatter
    has_frontmatter = output.strip().startswith("---") and output.count("---") >= 2
    
    # Check wikilinks
    wikilinks = len(re.findall(r'\[\[.*?\]\]', output))
    
    # Check code blocks
    code_blocks = len(re.findall(r'```python', output))
    
    # Check each code block is valid
    code_valid_count = 0
    for m in re.finditer(r'```python\s*\n(.*?)```', output, re.DOTALL):
        try:
            ast.parse(m.group(1))
            code_valid_count += 1
        except: pass
    
    points = sum([has_frontmatter, wikilinks >= 2, code_blocks >= 3, code_valid_count >= 2])
    if points >= 3:
        return 100, f"Frontmatter:{has_frontmatter}, wikilinks:{wikilinks}, code blocks:{code_blocks}"
    elif points >= 2:
        return 50, f"Frontmatter:{has_frontmatter}, wikilinks:{wikilinks}, code blocks:{code_blocks}"
    else:
        return 0, f"Frontmatter:{has_frontmatter}, wikilinks:{wikilinks}, code blocks:{code_blocks}"

def score_rwt4(output: str) -> tuple[int, str]:
    """RWT-4: Web extraction."""
    has_url = bool(re.search(r'https?://[^\s]+', output))
    has_headers = len(re.findall(r'^#{1,3}\s', output, re.MULTILINE)) >= 2
    word_count = len(output.split())
    size_ok = 100 < word_count < 2000
    has_ssl = "ssl" in output.lower() or "SSL" in output or "verify" in output.lower()
    
    points = sum([has_url, has_headers, size_ok, has_ssl])
    if points >= 3:
        return 100, f"URL:{has_url}, structured:{has_headers}, SSL:{has_ssl}, size:{word_count}w"
    elif points >= 2:
        return 50, f"URL:{has_url}, structured:{has_headers}, SSL:{has_ssl}, size:{word_count}w"
    else:
        return 0, f"URL:{has_url}, structured:{has_headers}, SSL:{has_ssl}, size:{word_count}w"

# ── Framework path (Gemma + Tavily + memory) ───────────
def run_framework(task_id: str, task_desc: str, task_type="coding") -> dict:
    """Run task through the MAIBS framework manually (Tavily + Gemma).
    Simulates the solve_with_memory pipeline without MCP server dependency."""
    t0 = time.time()
    path_taken = []
    
    # 1. Experience index lookup
    exp_context = ""
    if os.path.exists(EXPERIENCE_INDEX):
        try:
            idx = open(EXPERIENCE_INDEX).read()
            # Simple keyword match
            keywords = set(task_desc.lower().split()) - {"a", "the", "in", "of", "to", "and", "is", "that", "for", "with", "on", "as", "by", "at", "an", "be", "it", "or"}
            relevant = []
            for line in idx.split("\n"):
                line_lower = line.lower()
                hits = sum(1 for k in keywords if k in line_lower)
                if hits >= 3:
                    relevant.append(line)
            if relevant:
                exp_context = "\n## EXPERIENCE (past solves)\n" + "\n".join(relevant[:5])
                path_taken.append("experience_index")
        except: pass
    
    # 2. Tavily web search
    web_context = tavily_snippet(task_desc)
    if web_context:
        path_taken.append("tavily_snippet")
    
    # 3. Build prompt
    prompt = f"""You are Gemma, a helpful coding assistant. Solve this task.

TASK: {task_desc}
"""
    if web_context:
        prompt += f"\n{web_context}\n"
    if exp_context:
        prompt += f"\n{exp_context}\n"
    
    prompt += "\nWrite the solution as clean Python code in a markdown code block.\n"
    
    # 4. Call Gemma
    output = call_gemma(prompt, timeout=300)
    
    # 5. If failed, try with more context
    if "ERROR:" in output:
        # Retry with just the task (stripped prompt)
        clean_prompt = f"TASK: {task_desc}\n\nWrite the solution as clean Python code in a markdown code block.\n"
        output = call_gemma(clean_prompt, timeout=300)
    
    elapsed = time.time() - t0
    
    result = {
        "task_id": task_id,
        "model": "Gemma 4 E4B + framework",
        "output": output,
        "path_taken": path_taken,
        "elapsed": round(elapsed, 1),
        "web_context_used": bool(web_context),
        "experience_used": bool(exp_context),
    }
    return result

# ── Bare frontier path ─────────────────────────────────
def run_frontier(task_id: str, task_desc: str) -> dict:
    """Run task through bare frontier model — NO tools, NO context injection."""
    t0 = time.time()
    prompt = f"TASK: {task_desc}\n\nWrite the solution as clean Python code in a markdown code block.\n"
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

# ── RWT Tasks ──────────────────────────────────────────
RWT_TASKS = {
    "RWT-1": {
        "title": "Live Docs Lookup",
        "desc": "What changed in the Python requests library's latest release? Search the web to find the current version (requests 2.34.2 or newer). Summarize the key changes from the latest release notes, and show a working Python usage example for the newest feature. Include the source URL.",
        "type": "general",
        "scorer": score_rwt1,
        "priority": True,
    },
    "RWT-2": {
        "title": "Memory Carry-Over",
        "desc": "Write a function extract_domain(email: str) -> str that extracts the domain part of an email address. For example, 'user@example.com' returns 'example.com'. Use regex or string splitting. Check your past experience for similar email tasks you've solved before.",
        "type": "coding",
        "scorer": score_rwt2,
        "priority": True,
        "setup": "Write a function validate_email(email: str) -> bool that checks if a string is a valid email address format using regex.",
    },
    "RWT-5": {
        "title": "Bug-Fix with History",
        "desc": "Write a function get_middle_third(items: list) -> list that returns the middle third of a list. For a list of length N, return elements from index N//3 to index 2*N//3 (inclusive). Handle edge cases: empty list returns empty list.",
        "type": "coding",
        "scorer": score_rwt5,
        "priority": True,
        "setup": "Write a function get_range(items: list, start: int, end: int) -> list that returns all elements from index start to index end (inclusive) from a list. For example, get_range([1,2,3,4,5], 1, 3) returns [2,3,4].",
    },
    "RWT-6": {
        "title": "Current API Coding",
        "desc": "Write a Python function get_repo_info(owner: str, repo: str) -> dict that calls the GitHub REST API to get repository information. Search the web for the current GitHub API v3 REST endpoint format and required headers. The function should: (1) Use the correct current API endpoint, (2) Include proper headers like Accept: application/vnd.github+json, (3) Handle rate limiting by checking for 403 status and X-RateLimit-Remaining header, (4) Return a dict with: name, stars (stargazers_count), language, open_issues.",
        "type": "coding",
        "scorer": score_rwt6,
        "priority": True,
    },
    "RWT-3": {
        "title": "Wiki Authoring",
        "desc": "Write a wiki page about Python list comprehensions. Include YAML frontmatter with title, created date (2026-06-11), and tags. Include at least 2 wikilinks to related pages in [[page-name]] format. Include 3 code examples of increasing complexity, each in a ```python code block.",
        "type": "general",
        "scorer": score_rwt3,
        "priority": False,
    },
    "RWT-4": {
        "title": "Web Extraction",
        "desc": "Read the Python requests library documentation at https://docs.python-requests.org/en/latest/user/quickstart/ and extract: (1) The 3 most common HTTP methods shown, (2) One example for each method, (3) Any warning or note about SSL verification. Save as a structured summary with clear sections.",
        "type": "general",
        "scorer": score_rwt4,
        "priority": False,
    },
    "RWT-7": {
        "title": "Multi-Step Orchestration",
        "desc": "Build a data pipeline with 3 steps: Step 1: Write fetch_user_data() returning a list of 5 user dicts with keys name, email, age (include ages under and over 18). Step 2: Write filter_adults(users) returning users where age >= 18. Step 3: Write extract_emails(users) returning a list of email strings. Then write main() that chains all three: fetch -> filter -> extract -> print.",
        "type": "coding",
        "scorer": score_rwt7,
        "priority": False,
    },
}

# ── Main runner ────────────────────────────────────────
def main():
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    results = []
    priority_order = ["RWT-1", "RWT-2", "RWT-5", "RWT-6", "RWT-3", "RWT-4", "RWT-7"]
    
    for task_id in priority_order:
        task = RWT_TASKS[task_id]
        print(f"\n{'='*60}", flush=True)
        print(f"Running {task_id}: {task['title']}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # ── Setup tasks (seed experience for RWT-2 and RWT-5) ──
        if "setup" in task:
            setup_desc = task["setup"]
            print(f"  Seeding experience: {setup_desc[:80]}...")
            setup_result = run_framework(f"{task_id}-setup", setup_desc)
            print(f"  Setup done: {setup_result['elapsed']}s, path={setup_result['path_taken']}")
            # Small pause for experience to be written
            time.sleep(1)
        
        # ── Framework run ──
        print(f"  [Gemma+framework] Running...")
        fw_result = run_framework(task_id, task["desc"], task.get("type", "coding"))
        fw_score, fw_note = task["scorer"](fw_result["output"])
        fw_result["score"] = fw_score
        fw_result["score_note"] = fw_note
        print(f"  [Gemma+framework] Score: {fw_score}/100 — {fw_note}")
        print(f"  [Gemma+framework] Path: {fw_result['path_taken']}, Time: {fw_result['elapsed']}s")
        
        # ── Frontier run ──
        print(f"  [Frontier bare] Running...")
        fr_result = run_frontier(task_id, task["desc"])
        fr_score, fr_note = task["scorer"](fr_result["output"])
        fr_result["score"] = fr_score
        fr_result["score_note"] = fr_note
        print(f"  [Frontier bare] Score: {fr_score}/100 — {fr_note}")
        print(f"  [Frontier bare] Time: {fr_result['elapsed']}s")
        
        # ── Save raw outputs ──
        for prefix, res in [("fw", fw_result), ("fr", fr_result)]:
            outpath = f"{RESULTS_DIR}/{task_id}_{prefix}.txt"
            with open(outpath, "w") as f:
                f.write(f"Task: {task_id} — {task['title']}\n")
                f.write(f"Model: {res['model']}\n")
                f.write(f"Score: {res['score']}/100 — {res['score_note']}\n")
                f.write(f"Path: {res['path_taken']}\n")
                f.write(f"Elapsed: {res['elapsed']}s\n")
                f.write(f"Web context: {res['web_context_used']}\n")
                f.write(f"Experience used: {res['experience_used']}\n")
                f.write(f"\n{'─'*60}\nOUTPUT:\n{'─'*60}\n")
                f.write(res['output'])
        
        results.append({
            "task_id": task_id,
            "title": task["title"],
            "priority": task["priority"],
            "gemma_score": fw_score,
            "gemma_note": fw_note,
            "gemma_path": fw_result["path_taken"],
            "gemma_time": fw_result["elapsed"],
            "frontier_score": fr_score,
            "frontier_note": fr_note,
            "frontier_time": fr_result["elapsed"],
        })
        
        # Brief pause between tasks
        time.sleep(2)
    
    # ── Summary report ──────────────────────────────────
    print(f"\n{'='*60}")
    print("RWT RESULTS SUMMARY")
    print(f"{'='*60}")
    
    # Priority first
    print("\n## Priority Tasks (1, 2, 5, 6)")
    for r in results:
        if r["priority"]:
            print(f"  {r['task_id']} {r['title']}:")
            print(f"    Gemma+fw: {r['gemma_score']}/100 — {r['gemma_note']}")
            print(f"    Frontier: {r['frontier_score']}/100 — {r['frontier_note']}")
            print(f"    Gemma path: {r['gemma_path']}")
    
    print("\n## Secondary Tasks (3, 4, 7)")
    for r in results:
        if not r["priority"]:
            print(f"  {r['task_id']} {r['title']}:")
            print(f"    Gemma+fw: {r['gemma_score']}/100 — {r['gemma_note']}")
            print(f"    Frontier: {r['frontier_score']}/100 — {r['frontier_note']}")
    
    # ── Save JSON summary ──
    summary_path = f"{RESULTS_DIR}/summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {RESULTS_DIR}/")
    print(f"Summary: {summary_path}")
    
    return results

if __name__ == "__main__":
    main()
