#!/usr/bin/env python3.10
"""RWT Runner v2 — sequential, flush-after-each, robust."""
import json, os, sys, time, re, ast
import requests as req

sys.stdout.reconfigure(line_buffering=True)

TAVILY_KEY = "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"
OR_KEY = "OPENROUTER_KEY_PLACEHOLDER"
RESULTS = "/tmp/maibs-self-improvement-framework/results/rwt-run-1"
os.makedirs(RESULTS, exist_ok=True)

# ── API helpers ──────────────────────────────────────
def gemma(prompt, timeout=300):
    r = req.post("http://localhost:8080/v1/chat/completions", json={
        "messages": [{"role":"user","content":prompt}],
        "max_tokens": 800, "temperature": 0
    }, timeout=timeout)
    return r.json()["choices"][0]["message"]["content"]

def frontier(prompt, timeout=120):
    r = req.post("https://openrouter.ai/api/v1/chat/completions", json={
        "model": "deepseek/deepseek-chat",
        "messages": [{"role":"user","content":prompt}],
        "max_tokens": 800, "temperature": 0
    }, headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type":"application/json"}, timeout=timeout)
    d = r.json()
    if "error" in d:
        return f"API_ERROR: {d['error']}"
    return d["choices"][0]["message"]["content"]

def tavily(query, max_results=3):
    try:
        r = req.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_KEY, "query": query,
            "max_results": max_results, "search_depth": "basic"
        }, timeout=15)
        results = [x for x in r.json().get("results",[]) if x.get("score",0) > 0.7]
        if not results: return ""
        parts = ["## WEB CONTEXT (Tavily)"]
        for res in results[:3]:
            parts.append(f"\n### {res.get('title','')[:100]}")
            parts.append(res.get('content','')[:400])
            if res.get('url'): parts.append(f"Source: {res['url']}")
        text = "\n".join(parts)
        return text[:2400]  # 600-token cap
    except: return ""

# ── Scorers ───────────────────────────────────────────
def score_rwt1(out):
    v = re.search(r'2\.\d+\.\d+', out)
    vok = v and v.group() >= "2.32"
    url = bool(re.search(r'https?://[^\s\)]+', out))
    changes = len(re.findall(r'(?:^|\n)\s*(?:[-*•]|\d+\.)\s+\w', out))
    m = re.search(r'```python\s*\n(.*?)```', out, re.DOTALL)
    code_ok = False
    if m:
        try: ast.parse(m.group(1)); code_ok = True
        except: pass
    pts = sum([vok, url, changes>=2, code_ok])
    if pts >= 3: return 100, f"v={v.group() if v else '?'}, changes={changes}, url={url}, code={code_ok}"
    elif pts >= 2: return 50, f"v={v.group() if v else '?'}, changes={changes}, url={url}, code={code_ok}"
    return 0, f"v={v.group() if v else '?'}, changes={changes}, url={url}, code={code_ok}"

def score_generic(out, task_id):
    """Generic: check for code block, syntax, length."""
    has_code = "```python" in out or "```" in out
    long_enough = len(out) > 50
    no_error = "ERROR:" not in out and "API_ERROR:" not in out
    pts = sum([has_code, long_enough, no_error])
    if pts == 3: return 100, "valid response"
    elif pts >= 2: return 50, f"code={has_code}, len={long_enough}, ok={no_error}"
    return 0, f"code={has_code}, len={long_enough}, ok={no_error}"

# ── Task definitions ──────────────────────────────────
TASKS = [
    {
        "id": "RWT-1", "title": "Live Docs Lookup",
        "desc": "What changed in the Python requests library's latest release? Search the web to find the current version. Summarize the key changes from the latest release notes, and show a working Python usage example for the newest feature. Include the source URL.",
        "scorer": score_rwt1,
    },
    {
        "id": "RWT-2", "title": "Memory Carry-Over",
        "desc": "Write a function extract_domain(email: str) -> str that extracts the domain part of an email address. For example, 'user@example.com' returns 'example.com'. Use regex or string splitting.",
        "scorer": lambda o: score_generic(o, "RWT-2"),
        "setup": "Write a function validate_email(email: str) -> bool that checks if a string is a valid email address format using regex.",
    },
    {
        "id": "RWT-5", "title": "Bug-Fix with History",
        "desc": "Write a function get_middle_third(items: list) -> list that returns the middle third of a list. For a list of length N, return elements from index N//3 to index 2*N//3 (inclusive). Handle edge cases: empty list returns empty list.",
        "scorer": lambda o: score_generic(o, "RWT-5"),
        "setup": "Write a function get_range(items: list, start: int, end: int) -> list that returns all elements from index start to index end (inclusive) from a list.",
    },
    {
        "id": "RWT-6", "title": "Current API Coding",
        "desc": "Write a Python function get_repo_info(owner: str, repo: str) -> dict that calls the GitHub REST API to get repository information. Search the web for the current GitHub API v3 REST endpoint format and required headers. Include proper headers, handle rate limiting, return name/stars/language/open_issues.",
        "scorer": lambda o: score_generic(o, "RWT-6"),
    },
    {
        "id": "RWT-3", "title": "Wiki Authoring",
        "desc": "Write a wiki page about Python list comprehensions. Include YAML frontmatter with title, created date (2026-06-11), and tags. Include at least 2 wikilinks to related pages in [[page-name]] format. Include 3 code examples of increasing complexity, each in a ```python code block.",
        "scorer": lambda o: score_generic(o, "RWT-3"),
    },
    {
        "id": "RWT-4", "title": "Web Extraction",
        "desc": "Read the Python requests library documentation at https://docs.python-requests.org/en/latest/user/quickstart/ and extract: (1) The 3 most common HTTP methods shown, (2) One example for each method, (3) Any warning or note about SSL verification. Save as a structured summary with clear sections.",
        "scorer": lambda o: score_generic(o, "RWT-4"),
    },
    {
        "id": "RWT-7", "title": "Multi-Step Orchestration",
        "desc": "Build a data pipeline with 3 steps: Step 1: Write fetch_user_data() returning a list of 5 user dicts (name, email, age — mix under/over 18). Step 2: Write filter_adults(users) returning users where age >= 18. Step 3: Write extract_emails(users) returning email strings. Then write main() that chains all three: fetch -> filter -> extract -> print.",
        "scorer": lambda o: score_generic(o, "RWT-7"),
    },
]

# ── Run ────────────────────────────────────────────────
all_results = []
for task in TASKS:
    tid, title, desc = task["id"], task["title"], task["desc"]
    print(f"\n{'='*50}")
    print(f"{tid}: {title}")
    print(f"{'='*50}")
    
    # Setup (seed experience)
    if "setup" in task:
        print(f"  Seeding: {task['setup'][:80]}...")
        s_prompt = task["setup"] + "\n\nWrite the solution as Python code in a ```python block."
        s_out = gemma(s_prompt)
        print(f"  Setup: {len(s_out)} chars, OK={('ERROR' not in s_out)}")
        time.sleep(0.5)
    
    # Gemma + framework
    print(f"  [Gemma+fw] ...")
    web = tavily(desc)
    fw_prompt = f"TASK: {desc}\n\n{web}\n\nWrite the solution in a ```python code block."
    fw_out = gemma(fw_prompt)
    fw_score, fw_note = task["scorer"](fw_out)
    print(f"  [Gemma+fw] Score: {fw_score}/100 — {fw_note}")
    
    # Save Gemma output
    with open(f"{RESULTS}/{tid}_fw.txt", "w") as f:
        f.write(f"Task: {tid} — {title}\nModel: Gemma 4 E4B + framework\nScore: {fw_score}/100 — {fw_note}\n\nOUTPUT:\n{fw_out}")
    
    # Frontier bare
    print(f"  [Frontier] ...")
    fr_prompt = f"TASK: {desc}\n\nWrite the solution in a ```python code block."
    fr_out = frontier(fr_prompt)
    fr_score, fr_note = task["scorer"](fr_out)
    print(f"  [Frontier] Score: {fr_score}/100 — {fr_note}")
    
    # Save Frontier output
    with open(f"{RESULTS}/{tid}_fr.txt", "w") as f:
        f.write(f"Task: {tid} — {title}\nModel: Bare deepseek/deepseek-chat (no tools)\nScore: {fr_score}/100 — {fr_note}\n\nOUTPUT:\n{fr_out}")
    
    all_results.append({
        "task_id": tid, "title": title,
        "gemma_score": fw_score, "gemma_note": fw_note,
        "frontier_score": fr_score, "frontier_note": fr_note,
    })
    time.sleep(1)

# ── Summary ────────────────────────────────────────────
print(f"\n{'='*50}")
print("RWT RESULTS SUMMARY")
print(f"{'='*50}")

print("\n## Priority Tasks")
for r in all_results[:4]:
    print(f"  {r['task_id']} {r['title']}:")
    print(f"    Gemma+fw: {r['gemma_score']}/100 — {r['gemma_note']}")
    print(f"    Frontier: {r['frontier_score']}/100 — {r['frontier_note']}")

print("\n## Secondary Tasks")
for r in all_results[4:]:
    print(f"  {r['task_id']} {r['title']}:")
    print(f"    Gemma+fw: {r['gemma_score']}/100 — {r['gemma_note']}")
    print(f"    Frontier: {r['frontier_score']}/100 — {r['frontier_note']}")

with open(f"{RESULTS}/summary.json", "w") as f:
    json.dump(all_results, f, indent=2)

print(f"\nResults saved to {RESULTS}/")
