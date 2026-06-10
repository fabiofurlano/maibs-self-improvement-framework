#!/usr/bin/env python3.10
"""
MAIBS MCP Server — exposes the self-improvement pipeline as a callable tool.

Protocol: JSON-RPC 2.0 over HTTP (FastAPI)
Port: 8282
Auth: API key via X-API-Key header or MAIBS_API_KEY env var

Exposed tool: solve_with_memory(task_description, task_type="coding")

Internal flow:
  1. Read EXPERIENCE_INDEX.md → inject relevant past patterns
  2. Detect library → Context7/web search for docs upfront
  3. First attempt (MiniMax M3 + context)
  4. Failure → inject failure memory → second attempt
  5. Still failing → DeepSeek V4 Pro reasoning lifeline → third attempt
  6. Still failing → web search fallback → final attempt
  7. On pass → write to EXPERIENCE_INDEX.md + detail file
  8. Return { solution, passed, attempts_used, path_taken }

Usage:
  python3 maibs_mcp_server.py
  # Or with API key: MAIBS_API_KEY=sk-xxx python3 maibs_mcp_server.py
"""
import json, os, re, sys, time, sqlite3, subprocess, hashlib, uuid
from datetime import datetime
from pathlib import Path

# ── FastAPI / uvicorn ────────────────────────────────
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("ERROR: fastapi + uvicorn required: pip install fastapi uvicorn")
    sys.exit(1)

# ── Config ───────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 8282
API_KEY = os.environ.get("MAIBS_API_KEY", "")

BASE_DIR = Path.home() / ".hermes/planning/self-improvement-loop"
DB_PATH = BASE_DIR / "experience.db"
TASKS_DIR = BASE_DIR / "tasks/mbpp"
REPO_DIR = Path("/tmp/maibs-self-improvement-framework")
EXPERIENCE_INDEX = REPO_DIR / "experiences/EXPERIENCE_INDEX.md"
EXPERIENCES_DIR = REPO_DIR / "experiences/coding"

# Ensure directories exist
EXPERIENCES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MAIBS MCP Server", version="1.0.0")

# ── Auth ─────────────────────────────────────────────
def check_auth(request: Request):
    if not API_KEY:
        return  # No auth configured — open access
    auth_header = request.headers.get("X-API-Key", "")
    if auth_header != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ── Library detection ─────────────────────────────────
LIBRARY_HINTS = {
    'numpy': ['array', 'matrix', 'vector', 'ndarray', 'linspace', 'arange', 'numpy'],
    'pandas': ['dataframe', 'series', 'csv', 'read_csv', 'groupby'],
    'math': ['sqrt', 'log', 'sin', 'cos', 'ceil', 'floor', 'pow', 'pi', 'math.'],
    'itertools': ['permutations', 'combinations', 'product', 'chain'],
    'collections': ['counter', 'deque', 'defaultdict', 'ordereddict', 'namedtuple'],
    're': ['regex', 'pattern', 're.match', 're.search', 're.sub', 're.findall'],
    'functools': ['reduce', 'lru_cache', 'partial'],
    'heapq': ['heap', 'heappush', 'heappop', 'nsmallest', 'nlargest'],
    'statistics': ['mean', 'median', 'stdev', 'variance'],
    'random': ['random.', 'randint', 'choice', 'shuffle', 'sample'],
}

def detect_library(task_description: str) -> str | None:
    desc_lower = task_description.lower()
    for lib, keywords in LIBRARY_HINTS.items():
        for kw in keywords:
            if kw in desc_lower:
                return lib
    return None

# ── Experience index operations ───────────────────────
def read_experience_index() -> list[dict]:
    """Read EXPERIENCE_INDEX.md, return entries as list of dicts."""
    if not EXPERIENCE_INDEX.exists():
        return []
    entries = []
    content = EXPERIENCE_INDEX.read_text()
    for line in content.split("\n"):
        # Parse: | `[category]` | scope | date | summary |
        if line.startswith("| `[") and "|" in line[3:]:
            parts = [p.strip().strip("`") for p in line.split("|")[1:-1]]
            if len(parts) >= 4:
                entries.append({
                    "category": parts[0].strip("[]"),
                    "scope": parts[1],
                    "date": parts[2],
                    "summary": parts[3],
                })
    return entries

def filter_experiences(entries: list[dict], task_type: str) -> str:
    """Filter entries by scope, return formatted context string."""
    scope_map = {"coding": "coding", "general": "general", "benchmark": "global"}
    target_scope = scope_map.get(task_type, "coding")
    
    relevant = [e for e in entries
                if e["scope"] in (target_scope, "global", "benchmark")]
    
    if not relevant:
        return ""
    
    lines = ["## Past Experience (from EXPERIENCE_INDEX)"]
    for e in relevant[:5]:  # Top 5 most relevant
        lines.append(f"- [{e['category']}] {e['summary']}")
    return "\n".join(lines)

def append_experience(category: str, scope: str, summary: str, detail_content: str = ""):
    """Append entry to index + write detail file."""
    entry_line = f"| `[{category}]` | {scope} | {datetime.now().strftime('%Y-%m-%d')} | {summary} |\n"
    
    # Read current index, find where to insert new entries
    content = EXPERIENCE_INDEX.read_text() if EXPERIENCE_INDEX.exists() else ""
    lines = content.split("\n")
    
    # Find the last detail files section and insert before it
    detail_idx = None
    for i, line in enumerate(lines):
        if line.startswith("## Detail Files"):
            detail_idx = i
            break
    
    if detail_idx is not None:
        lines.insert(detail_idx, entry_line.rstrip())
    else:
        lines.append(entry_line.rstrip())
    
    EXPERIENCE_INDEX.write_text("\n".join(lines) + "\n")
    
    # Write detail file if content provided
    if detail_content:
        slug = re.sub(r'[^a-z0-9]+', '-', summary.lower())[:50]
        detail_path = EXPERIENCES_DIR / f"{slug}.md"
        detail_path.write_text(detail_content)

# ── LLM calls ─────────────────────────────────────────
def call_m3(prompt: str, timeout: int = 180) -> tuple[str, float]:
    """Call MiniMax M3 via hermes CLI. Returns (output, elapsed_seconds)."""
    t0 = time.time()
    try:
        r = subprocess.run(
            ["hermes", "-z", prompt, "-m", "MiniMax-M3", "--provider", "minimax"],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "HOME": str(Path.home())}
        )
        return r.stdout, time.time() - t0
    except subprocess.TimeoutExpired:
        return "", timeout
    except Exception as e:
        return f"ERROR: {e}", time.time() - t0

def call_deepseek(problem: str, attempts: list[dict]) -> str:
    """Call DeepSeek V4 Pro for reasoning analysis."""
    attempt_text = ""
    for i, a in enumerate(attempts, 1):
        attempt_text += f"""
ATTEMPT {i} (FAILED):
```python
{a.get('code', '')[:500]}
```
Error: {a.get('error', 'unknown')}
"""

    prompt = f"""You are a coding expert helping a weaker model solve a Python problem.

PROBLEM:
{problem}

{attempt_text}

Analyze each failed attempt. Identify WHY each one failed. Explain the CORRECT approach. Then write the correct solution as a Python function in a markdown code block.

Your response format:
## Analysis
(why each attempt failed)

## Correct Approach
(what the right solution looks like)

## Solution
```python
(the correct function code)
```"""
    
    output, elapsed = call_deepseek_raw(prompt)
    return output

def call_deepseek_raw(prompt: str) -> tuple[str, float]:
    """Raw DeepSeek call."""
    t0 = time.time()
    try:
        r = subprocess.run(
            ["hermes", "-z", prompt, "-m", "deepseek-v4-pro", "--provider", "opencode-go"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": str(Path.home())}
        )
        return r.stdout, time.time() - t0
    except subprocess.TimeoutExpired:
        return "", 120
    except Exception as e:
        return f"ERROR: {e}", time.time() - t0

# ── Web search ────────────────────────────────────────
def web_search(query: str) -> str:
    """Search DuckDuckGo, return formatted context."""
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(f"{query} Python implementation", max_results=3))
        if not results:
            return ""
        parts = []
        for r in results[:2]:
            body = r.get('body', '')[:400]
            title = r.get('title', '')
            url = r.get('href', '')
            if body:
                parts.append(f"**{title}**\n{body}\nSource: {url}")
        return "\n\n".join(parts) if parts else ""
    except Exception as e:
        return f"[web search error: {e}]"

# ── Context7 stub ─────────────────────────────────────
def context7_lookup(lib: str, task: str) -> str:
    """Search for library-specific implementation docs."""
    return web_search(f"{lib} Python {task[:80]} example")

# ── Oracle (code validation) ──────────────────────────
def run_oracle(code: str, test_setup: str, test_list: list[str]) -> tuple[bool, str]:
    """Run test assertions against generated code. Returns (passed, error)."""
    full_code = (test_setup or "") + "\n" + code + "\n" + "\n".join(test_list)
    try:
        exec(full_code, {})
        return True, ""
    except AssertionError as e:
        return False, f"AssertionError: {str(e)[:200]}"
    except SyntaxError as e:
        return False, f"SyntaxError: {str(e)[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"

# ── Code extraction ───────────────────────────────────
def extract_code(output: str) -> str:
    """Extract Python code from markdown code block in LLM output."""
    lines = output.split("\n")
    in_block = False
    code_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            code_lines.append(line)
    return "\n".join(code_lines) if code_lines else output

# ═══════════════════════════════════════════════════════
#  CORE: solve_with_memory
# ═══════════════════════════════════════════════════════
def solve_with_memory(task_description: str, task_type: str = "coding",
                      test_setup: str = "", test_list: list[str] | None = None) -> dict:
    """
    Run the full self-improvement pipeline on a task.
    
    Returns: { solution, passed, attempts_used, path_taken, error }
    """
    path_taken = []
    attempts = []
    context_blocks = []
    solution = ""
    error = ""
    passed = False
    
    # ── Layer 0: EXPERIENCE_INDEX ─────────────────
    entries = read_experience_index()
    if entries:
        exp_context = filter_experiences(entries, task_type)
        if exp_context:
            context_blocks.append(exp_context)
            path_taken.append("experience_index")
    
    # ── Layer 0.5: Context7 for library tasks ──────
    lib = detect_library(task_description)
    if lib:
        c7_result = context7_lookup(lib, task_description)
        if c7_result:
            context_blocks.append(f"## Library Documentation ({lib})\n{c7_result[:1200]}")
            path_taken.append(f"context7:{lib}")
    
    # ── Build base prompt ──────────────────────────
    def build_prompt(extra_context: str = "", failure_memory: str = "", 
                     reasoning: str = "", search_result: str = "") -> str:
        parts = []
        for block in context_blocks:
            parts.append(block)
        if failure_memory:
            parts.append(failure_memory)
        if reasoning:
            parts.append(reasoning)
        if search_result:
            parts.append(search_result)
        if extra_context:
            parts.append(extra_context)
        
        context_str = "\n\n".join(parts) if parts else ""
        
        return f"""{context_str}

Write a Python function that solves this problem. Return ONLY the function code in a single markdown code block.

Problem: {task_description}

```python
# Your solution here
```"""
    
    # ── Attempt 1: Base context only ──────────────
    prompt1 = build_prompt()
    output1, t1 = call_m3(prompt1)
    code1 = extract_code(output1)
    passed1, err1 = run_oracle(code1, test_setup, test_list or [])
    attempts.append({"code": code1[:500], "error": err1, "time": t1})
    
    if passed1:
        solution = code1
        passed = True
        path_taken.append("attempt_1_pass")
        _write_success(task_description, code1, 1, path_taken)
        return _build_response(solution, True, attempts, path_taken, "")
    
    path_taken.append("attempt_1_fail")
    
    # ── Attempt 2: Failure memory ─────────────────
    failure_memory = f"""## YOUR PREVIOUS ATTEMPT (FAILED)

```python
{code1[:300]}
```
Error: {err1}

**Learn from this mistake.** Correct the error and write a working solution."""
    
    prompt2 = build_prompt(failure_memory=failure_memory)
    output2, t2 = call_m3(prompt2)
    code2 = extract_code(output2)
    passed2, err2 = run_oracle(code2, test_setup, test_list or [])
    attempts.append({"code": code2[:500], "error": err2, "time": t2})
    
    if passed2:
        solution = code2
        passed = True
        path_taken.append("attempt_2_pass")
        _write_success(task_description, code2, 2, path_taken)
        return _build_response(solution, True, attempts, path_taken, "")
    
    path_taken.append("attempt_2_fail")
    
    # ── Attempt 3: DeepSeek reasoning lifeline ────
    reasoning = call_deepseek(task_description, attempts)
    reasoning_block = f"""## EXPERT ANALYSIS (DeepSeek V4 Pro)

A stronger model analyzed your failures:

{reasoning[:1500]}

---
Now write the CORRECT solution."""
    
    prompt3 = build_prompt(reasoning=reasoning_block)
    output3, t3 = call_m3(prompt3)
    code3 = extract_code(output3)
    passed3, err3 = run_oracle(code3, test_setup, test_list or [])
    attempts.append({"code": code3[:500], "error": err3, "time": t3})
    
    if passed3:
        solution = code3
        passed = True
        path_taken.append("attempt_3_pass_reasoning")
        _write_success(task_description, code3, 3, path_taken)
        return _build_response(solution, True, attempts, path_taken, "")
    
    path_taken.append("attempt_3_fail")
    
    # ── Attempt 4: Web search fallback ────────────
    search_result = web_search(task_description)
    search_block = ""
    if search_result:
        search_block = f"""## WEB SEARCH RESULTS

{search_result[:1200]}

---
Use this information to write the correct solution."""
        path_taken.append("web_search")
    
    prompt4 = build_prompt(reasoning=reasoning_block, search_result=search_block)
    output4, t4 = call_m3(prompt4)
    code4 = extract_code(output4)
    passed4, err4 = run_oracle(code4, test_setup, test_list or [])
    attempts.append({"code": code4[:500], "error": err4, "time": t4})
    
    if passed4:
        solution = code4
        passed = True
        path_taken.append("attempt_4_pass")
        _write_success(task_description, code4, 4, path_taken)
    else:
        path_taken.append("attempt_4_fail_all_exhausted")
        error = err4
    
    return _build_response(solution, passed, attempts, path_taken, error)

# ── Response builder ──────────────────────────────────
def _build_response(solution: str, passed: bool, attempts: list[dict],
                    path_taken: list[str], error: str) -> dict:
    return {
        "solution": solution[:2000],
        "passed": passed,
        "attempts_used": len(attempts),
        "path_taken": path_taken,
        "error": error,
        "attempt_details": [
            {"attempt": i+1, "error": a["error"][:100], "time_s": round(a["time"], 1)}
            for i, a in enumerate(attempts)
        ]
    }

def _write_success(task_description: str, solution: str, attempts: int,
                   path_taken: list[str]):
    """Write successful solve to EXPERIENCE_INDEX and detail file."""
    summary = f"pipeline solved in {attempts} attempt(s): {task_description[:80]}"
    detail = f"""# Pipeline Solve — {datetime.now().strftime('%Y-%m-%d %H:%M')}

**Task:** {task_description[:200]}

**Path taken:** {' → '.join(path_taken)}

**Solution:**
```python
{solution[:1000]}
```

**Attempts:** {attempts}
"""
    
    try:
        append_experience("solution", "coding", summary, detail)
    except Exception as e:
        print(f"[WARN] Failed to write experience: {e}")

# ═══════════════════════════════════════════════════════
#  FastAPI / JSON-RPC endpoints
# ═══════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "server": "MAIBS MCP Server",
        "version": "1.0.0",
        "tools": ["solve_with_memory"],
        "auth_required": bool(API_KEY),
    }

@app.post("/mcp")
async def mcp_handler(request: Request):
    check_auth(request)
    
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})
    rid = body.get("id")
    
    def rpc_result(result=None, error=None):
        d = {"jsonrpc": "2.0", "id": rid}
        d["result" if error is None else "error"] = result if error is None else error
        return JSONResponse(content=d)
    
    # ── initialize ────────────────────────────────
    if method == "initialize":
        return rpc_result({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "maibs-mcp", "version": "1.0.0"},
            "capabilities": {"tools": {}}
        })
    
    # ── tools/list ────────────────────────────────
    if method == "tools/list":
        return rpc_result({
            "tools": [{
                "name": "solve_with_memory",
                "description": "Run the MAIBS self-improvement pipeline on a coding task. Internally runs up to 4 attempts with progressively richer context: experience index → Context7/library docs → failure memory → DeepSeek reasoning → web search. Returns solution, pass/fail, attempt count, and path taken.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_description"],
                    "properties": {
                        "task_description": {
                            "type": "string",
                            "description": "The coding task description (e.g., 'Write a function to find the list with maximum length using lambda')"
                        },
                        "task_type": {
                            "type": "string",
                            "description": "Task category for experience index filtering: coding, general, benchmark",
                            "default": "coding"
                        },
                        "test_setup": {
                            "type": "string",
                            "description": "Optional setup code to run before test assertions (imports, helper functions)"
                        },
                        "test_list": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of assert statements to validate the solution"
                        }
                    }
                }
            }]
        })
    
    # ── tools/call ────────────────────────────────
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        if tool_name == "solve_with_memory":
            task_desc = arguments.get("task_description", "")
            if not task_desc:
                return rpc_result(error={"code": -32602, "message": "task_description is required"})
            
            task_type = arguments.get("task_type", "coding")
            test_setup = arguments.get("test_setup", "")
            test_list = arguments.get("test_list", [])
            
            result = solve_with_memory(task_desc, task_type, test_setup, test_list)
            
            return rpc_result({
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }]
            })
        
        return rpc_result(error={"code": -32601, "message": f"Unknown tool: {tool_name}"})
    
    # ── Unknown method ────────────────────────────
    return rpc_result(error={"code": -32601, "message": f"Method not found: {method}"})

# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    auth_msg = "API key required" if API_KEY else "no auth (open)"
    print(f"MAIBS MCP Server starting on {HOST}:{PORT} ({auth_msg})")
    print(f"Tool: solve_with_memory(task_description, task_type='coding')")
    print(f"Health: http://{HOST}:{PORT}/health")
    print(f"MCP:    POST http://{HOST}:{PORT}/mcp")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
