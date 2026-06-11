#!/usr/bin/env python3.10
"""
MAIBS MCP Server — exposes the self-improvement pipeline as a callable tool.

Pipeline: classify → safety-gate → memory-recall → solve → oracle → evaluate → verdict → memory-write

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
import json, os, re, sys, time, sqlite3, subprocess, hashlib, uuid, yaml
from datetime import datetime
from pathlib import Path

# ── FastAPI / uvicorn ────────────────────────────────
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn
    import httpx
except ImportError:
    print("ERROR: fastapi + uvicorn required: pip install fastapi uvicorn")
    sys.exit(1)

# ── Config ───────────────────────────────────────────
HOST = "0.0.0.0"
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
# Solver priority: local Gemma (free) → OpenRouter → Hermes CLI (M3)
LLAMA_URL = "http://localhost:8080/v1/chat/completions"
LLAMA_MODEL = "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"

import requests as _requests

def _llama_available() -> bool:
    try: return _requests.get("http://localhost:8080/health", timeout=2).status_code == 200
    except: return False

def call_gemma(prompt: str, timeout: int = 180) -> tuple[str, float]:
    """Call local Gemma 4 E4B via llama-server. Returns (output, elapsed_seconds)."""
    t0 = time.time()
    try:
        r = _requests.post(LLAMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500, "temperature": 0,
        }, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], time.time() - t0
    except Exception as e:
        return f"ERROR: {e}", time.time() - t0

def call_m3(prompt: str, timeout: int = 180) -> tuple[str, float]:
    """Call MiniMax M3 via hermes CLI (escalation backend). Returns (output, elapsed_seconds)."""
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

def call_solver(prompt: str, timeout: int = 180) -> tuple[str, float]:
    """Default solver: local Gemma. Falls back to Hermes CLI M3 if Gemma is down.
    Use call_m3() directly for explicit escalation (DeepSeek reasoning, etc)."""
    if _llama_available():
        return call_gemma(prompt, timeout)
    # Fall back to Hermes CLI M3
    return call_m3(prompt, timeout)

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

# ── Tavily snippet injection (RWT — before attempt 1) ──
def _tavily_snippet(prompt: str) -> str:
    """Get a compact WEB CONTEXT block via Tavily search+extract.
    Returns '' on any failure path. Never raises. ~600 token cap."""
    try:
        sys.path.insert(0, str(REPO_DIR / "scripts"))
        from tavily_snippet import get_snippet
        return get_snippet(prompt)
    except Exception:
        return ""


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
#  PHASE 7.5: Intent Classifier
# ═══════════════════════════════════════════════════════
INTENT_CLASSIFIER_SYSTEM = """You are a task router. Read the task and reply with exactly one word.

- clarify  → task is ambiguous, has missing required information, or contradicts itself
- plan     → task requires multiple steps or complex reasoning to complete
- execute  → task is clear, self-contained, can be done in one step

Reply with exactly one word: clarify | plan | execute"""

def classify_intent(task_description: str) -> str:
    """Route the task before spending any compute. Returns: clarify | plan | execute.
    Cheap Gemma call — fast, local, free."""
    prompt = f"{INTENT_CLASSIFIER_SYSTEM}\n\nTASK: {task_description}"
    output, _ = call_gemma(prompt, timeout=30)
    output = output.strip().lower()
    if "clarify" in output:
        return "clarify"
    if "plan" in output:
        return "plan"
    if "execute" in output:
        return "execute"
    return "execute"  # Default — never loop the classifier

# ═══════════════════════════════════════════════════════
#  PHASE 7.5: Safety Gate
# ═══════════════════════════════════════════════════════
SAFETY_GATE_SYSTEM = """You are a pre-execution safety checker. Examine the task for structural problems.

Check for:
1. Are all required inputs present? (function name, return type, test cases if coding)
2. Are there contradictions? (e.g., "return a string AND an integer")
3. Is the task format valid? (not empty, not malformed)

Reply with exactly one word if the task is ready:
GO

Reply with the reason if there is a clear structural problem:
BLOCK: (one sentence describing the problem)

Default to GO. Only BLOCK on clear, specific structural problems.
Do NOT block for "task might be hard" or "I'm not sure if this is solvable."
Only block for missing inputs, contradictions, or malformed tasks."""

def safety_gate(task_description: str, test_setup: str = "",
                test_list: list[str] | None = None) -> tuple[bool, str]:
    """Check structural readiness before attempt 1. Returns (go, block_reason).
    One check, one decision. Never loops."""
    context = f"Task: {task_description}"
    if test_setup:
        context += f"\nTest setup code: {test_setup[:200]}"
    if test_list:
        context += f"\nTest assertions: {str(test_list)[:200]}"

    prompt = f"{SAFETY_GATE_SYSTEM}\n\n{context}"
    output, _ = call_gemma(prompt, timeout=30)
    output = output.strip()

    if output.upper().startswith("BLOCK"):
        reason = output[5:].strip().lstrip(":").strip()
        reason = reason or "unspecified structural issue"
        return False, reason
    return True, ""

# ═══════════════════════════════════════════════════════
#  PHASE A: Evaluator Node
# ═══════════════════════════════════════════════════════
EVALUATOR_SYSTEM = """You are an output evaluator. You receive a task's ORIGINAL criteria and a proposed solution.
Check the solution against EVERY criterion. Reply in exactly this format:

VERDICT: PASS
or
VERDICT: REJECT
REASON: <one sentence, the SPECIFIC criterion that failed and how>

Do not suggest fixes. Do not rewrite the solution. Judge only.

CRITICAL: If the solution meets ALL criteria, you MUST return VERDICT: PASS.
If the solution violates ANY single criterion, you MUST return VERDICT: REJECT.
When in doubt, check the code literally against each criterion."""

def evaluate_output(solution: str, original_criteria: str) -> tuple[bool, str]:
    """Check solution compliance against original criteria. Returns (passed, reason).
    Gemma E4B, think:false, fast rejection loop."""
    prompt = (
        f"{EVALUATOR_SYSTEM}\n\n"
        f"ORIGINAL CRITERIA:\n{original_criteria}\n\n"
        f"PROPOSED SOLUTION:\n```python\n{solution}\n```"
    )
    output, _ = call_gemma(prompt, timeout=60)
    output = output.strip()
    
    passed = True
    reason = ""
    
    for line in output.split("\n"):
        upper = line.strip().upper()
        if upper.startswith("VERDICT:"):
            verdict_part = upper.split(":", 1)[1].strip() if ":" in upper else ""
            passed = "PASS" in verdict_part and "REJECT" not in verdict_part
        if upper.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""
    
    if not passed and not reason:
        reason = "criteria not met (evaluator returned REJECT without reason)"
    
    return passed, reason

# ═══════════════════════════════════════════════════════
#  CORE: solve_with_memory
# ═══════════════════════════════════════════════════════
def solve_with_memory(task_description: str, task_type: str = "coding",
                      test_setup: str = "", test_list: list[str] | None = None,
                      original_criteria: str = "") -> dict:
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
    evaluator_rejections = 0  # Phase A: max 3 before reasoning lifeline
    
    # ── Phase 7.5: Intent Classifier ───────────────
    intent = classify_intent(task_description)
    path_taken.append(f"intent:{intent}")
    
    if intent == "clarify":
        return _build_response("", False, [], path_taken,
            f"Task needs clarification. Intent classifier returned 'clarify'. "
            f"Please provide more detail or rephrase the task.")
    
    # ── Phase 7.5: Safety Gate ─────────────────────
    go, block_reason = safety_gate(task_description, test_setup, test_list)
    if not go:
        return _build_response("", False, [], path_taken,
            f"Safety gate blocked: {block_reason}")
    path_taken.append("safety_gate:GO")
    
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
    
    # ── Layer 0.6: Tavily snippet (RWT — before attempt 1) ─
    snippet = _tavily_snippet(task_description)
    if snippet:
        context_blocks.append(snippet)
        path_taken.append("tavily_snippet")
    
    # ── Build base prompt ──────────────────────────
    # WEB CONTEXT override instruction — forces model to prefer injected data
    WEB_OVERRIDE = """!!! CRITICAL — READ THIS FIRST !!!

The ## WEB CONTEXT block below contains CURRENT, VERIFIED information retrieved
from live web searches performed RIGHT NOW. This data is authoritative.

YOU MUST use the information in the WEB CONTEXT block. Do NOT rely on your
training data for anything covered in the WEB CONTEXT. If the WEB CONTEXT says
X, the answer is X — even if your training data says something different.

Your training cutoff is early 2025. The WEB CONTEXT is from TODAY.
The web data is CORRECT. Your training data is STALE."""
    
    def build_prompt(extra_context: str = "", failure_memory: str = "", 
                     reasoning: str = "", search_result: str = "") -> str:
        parts = []
        has_web_context = False
        for block in context_blocks:
            if "WEB CONTEXT" in block:
                has_web_context = True
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
        
        # If WEB CONTEXT is present, prepend the override instruction
        top_instruction = f"{WEB_OVERRIDE}\n\n" if has_web_context else ""
        
        return f"""{top_instruction}{context_str}

Write a Python function that solves this problem. Return ONLY the function code in a single markdown code block.

Problem: {task_description}

```python
# Your solution here
```"""
    
    # ── Attempt 1: Base context only ──────────────
    prompt1 = build_prompt()
    output1, t1 = call_solver(prompt1)
    code1 = extract_code(output1)
    passed1, err1 = run_oracle(code1, test_setup, test_list or [])
    attempts.append({"code": code1[:500], "error": err1, "time": t1})
    
    if passed1:
        if original_criteria:
            ev_passed, ev_reason = evaluate_output(code1, original_criteria)
            if not ev_passed:
                evaluator_rejections += 1
                err1 = f"Evaluator REJECTED: {ev_reason}"
                path_taken.append(f"evaluator_reject_{evaluator_rejections}")
            else:
                solution = code1
                passed = True
                path_taken.append("attempt_1_pass_evaluator_pass")
                _write_success(task_description, code1, 1, path_taken)
                return _build_response(solution, True, attempts, path_taken, "")
        else:
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
    output2, t2 = call_solver(prompt2)
    code2 = extract_code(output2)
    passed2, err2 = run_oracle(code2, test_setup, test_list or [])
    attempts.append({"code": code2[:500], "error": err2, "time": t2})
    
    if passed2:
        if original_criteria:
            ev_passed, ev_reason = evaluate_output(code2, original_criteria)
            if not ev_passed:
                evaluator_rejections += 1
                err2 = f"Evaluator REJECTED: {ev_reason}"
                path_taken.append(f"evaluator_reject_{evaluator_rejections}")
            else:
                solution = code2
                passed = True
                path_taken.append("attempt_2_pass_evaluator_pass")
                _write_success(task_description, code2, 2, path_taken)
                return _build_response(solution, True, attempts, path_taken, "")
        else:
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
    output3, t3 = call_solver(prompt3)
    code3 = extract_code(output3)
    passed3, err3 = run_oracle(code3, test_setup, test_list or [])
    attempts.append({"code": code3[:500], "error": err3, "time": t3})
    
    if passed3:
        if original_criteria:
            ev_passed, ev_reason = evaluate_output(code3, original_criteria)
            if not ev_passed:
                evaluator_rejections += 1
                err3 = f"Evaluator REJECTED: {ev_reason}"
                path_taken.append(f"evaluator_reject_{evaluator_rejections}")
            else:
                solution = code3
                passed = True
                path_taken.append("attempt_3_pass_evaluator_pass")
                _write_success(task_description, code3, 3, path_taken)
                return _build_response(solution, True, attempts, path_taken, "")
        else:
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
    output4, t4 = call_solver(prompt4)
    code4 = extract_code(output4)
    passed4, err4 = run_oracle(code4, test_setup, test_list or [])
    attempts.append({"code": code4[:500], "error": err4, "time": t4})
    
    if passed4:
        if original_criteria:
            ev_passed, ev_reason = evaluate_output(code4, original_criteria)
            if not ev_passed:
                evaluator_rejections += 1
                err4 = f"Evaluator REJECTED: {ev_reason}"
                path_taken.append(f"evaluator_reject_{evaluator_rejections}")
            else:
                solution = code4
                passed = True
                path_taken.append("attempt_4_pass_evaluator_pass")
                _write_success(task_description, code4, 4, path_taken)
        else:
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
    solver = "gemma-4-e4b-local" if _llama_available() else "minimax-m3-api"
    return {
        "solution": solution[:2000],
        "passed": passed,
        "solver": solver,
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
                "description": "Run the MAIBS self-improvement pipeline on a coding task. Internally runs up to 4 attempts with progressively richer context: experience index → Context7/library docs → failure memory → DeepSeek reasoning → web search. Evaluator node (Phase A) checks criteria compliance after each oracle-pass. Returns solution, pass/fail, attempt count, and path taken.",
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
                        },
                        "original_criteria": {
                            "type": "string",
                            "description": "Optional explicit criteria beyond assertions. Evaluator node checks solution against every criterion (e.g., 'must use recursion', 'no external libraries')"
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
            original_criteria = arguments.get("original_criteria", "")
            
            result = solve_with_memory(task_desc, task_type, test_setup, test_list, original_criteria)
            
            return rpc_result({
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }]
            })
        
        return rpc_result(error={"code": -32601, "message": f"Unknown tool: {tool_name}"})
    
    # ── notifications/initialized ──────────────────
    if method == "notifications/initialized":
        # Client confirms it's ready after initialize. Ack with empty 200.
        return JSONResponse(content={"jsonrpc":"2.0","id":rid,"result":{}})
    
    # ── Unknown method ────────────────────────────
    return rpc_result(error={"code": -32601, "message": f"Method not found: {method}"})

# ── GET /mcp: SSE session endpoint (required by Claude Code, Codex, Hermes) ─
@app.get("/mcp")
async def mcp_get(request: Request):
    """Open an SSE stream for MCP session lifecycle.
    Standard clients open GET /mcp with Accept: text/event-stream to establish
    a session. We return an SSE stream with an initial session-id event and
    keep the connection alive for server→client push."""
    from starlette.responses import StreamingResponse
    import asyncio
    
    session_id = f"maibs-{uuid.uuid4().hex[:12]}"
    
    async def event_stream():
        # First event: session established
        yield f"event: session\ndata: {{\"session_id\":\"{session_id}\"}}\n\n"
        # Keep connection alive with periodic heartbeats
        while True:
            await asyncio.sleep(30)
            yield f": heartbeat\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Mcp-Session-Id": session_id,
        }
    )

# ═══════════════════════════════════════════════════════
#  REST endpoints for dashboard
# ═══════════════════════════════════════════════════════

CONFIG_PATH = Path.home() / ".maibs/config.yaml"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}

def _write_config(data: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

@app.get("/api/config")
async def get_config(request: Request):
    check_auth(request)
    return _read_config()

@app.put("/api/config")
async def put_config(request: Request):
    check_auth(request)
    body = await request.json()
    _write_config(body)
    return {"status": "ok", "path": str(CONFIG_PATH)}

@app.get("/api/stats")
async def get_stats(request: Request):
    check_auth(request)
    try:
        db = sqlite3.connect(str(DB_PATH))
        total = db.execute("SELECT COUNT(*) FROM experience").fetchone()[0]
        passes = db.execute("SELECT COUNT(*) FROM experience WHERE outcome='pass'").fetchone()[0]
        fails = db.execute("SELECT COUNT(*) FROM experience WHERE outcome='fail'").fetchone()[0]
        last_run = db.execute("SELECT MAX(timestamp) FROM experience").fetchone()[0]
        db.close()
    except Exception:
        total = passes = fails = 0
        last_run = None

    config = _read_config()
    pipeline = config.get("pipeline", {})
    backends = config.get("backends", {})

    return {
        "experience_count": total,
        "passes": passes,
        "fails": fails,
        "pass_rate": round(passes / total * 100, 1) if total else 0,
        "last_run": last_run,
        "backends": {
            "gemma": backends.get("local_gemma", {}).get("enabled", True),
            "openrouter": backends.get("openrouter", {}).get("enabled", True),
        },
        "pipeline": {k: v.get("enabled", True) for k, v in pipeline.items()},
        "runtime": config.get("runtime", {}).get("max_attempts", 4),
    }

@app.get("/api/experiences")
async def get_experiences(request: Request, limit: int = 20, offset: int = 0, q: str = "", tag: str = "", model: str = ""):
    check_auth(request)
    try:
        db = sqlite3.connect(str(DB_PATH))
        query = "SELECT id, task_id, approach_tried, outcome, verdict, timestamp, confidence, run_number FROM experience"
        conditions = []
        params = []
        if q:
            conditions.append("(task_id LIKE ? OR verdict LIKE ? OR approach_tried LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if tag:
            conditions.append("outcome = ?")
            params.append(tag)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit + 1, offset])

        rows = db.execute(query, params).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]

        total = db.execute("SELECT COUNT(*) FROM experience").fetchone()[0]
        db.close()

        entries = []
        for r in rows:
            entries.append({
                "id": f"exp-{r[0]:08x}",
                "task_id": r[1] or "unknown",
                "title": (r[2] or "")[:80].replace("\n", " ").strip(),
                "status": "PASS" if r[3] == "pass" else "FAIL",
                "preview": (r[4] or "")[:140],
                "timestamp": r[5],
                "confidence": r[6],
                "run": r[7],
            })
        return {"entries": entries, "has_more": has_more, "total": total}
    except Exception as e:
        return {"entries": [], "has_more": False, "total": 0, "error": str(e)}

@app.get("/api/experiences/export.jsonl")
async def export_experiences(request: Request):
    check_auth(request)
    try:
        db = sqlite3.connect(str(DB_PATH))
        rows = db.execute("SELECT * FROM experience ORDER BY timestamp DESC").fetchall()
        db.close()

        import io
        output = io.StringIO()
        for r in rows:
            entry = {
                "id": r[0], "task_id": r[2], "split": r[3],
                "outcome": r[4], "verdict": r[5], "why": r[6],
                "timestamp": r[7], "confidence": r[8], "run": r[10],
            }
            output.write(json.dumps(entry) + "\n")
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=maibs-experiences.jsonl"}
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/tools/test")
async def test_tools(request: Request):
    check_auth(request)
    body = await request.json()
    tools = body.get("tools", [])

    t0 = time.time()
    results = []

    for tool in tools:
        key_field = f"{tool}_api_key"
        config = _read_config()
        api_key = config.get("external_tools", {}).get(key_field, "") or config.get(key_field, "")

        if not api_key:
            results.append({"tool": tool, "status": 401, "latency_ms": 0, "error": "no API key configured"})
            continue

        t_tool = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if tool == "tavily":
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": api_key, "query": "test", "max_results": 1},
                        headers={"Content-Type": "application/json"}
                    )
                elif tool == "context7":
                    resp = await client.get(
                        "https://api.context7.com/v1",
                        headers={"Authorization": f"Bearer {api_key}"}
                    )
                else:
                    results.append({"tool": tool, "status": 400, "latency_ms": 0, "error": "unknown tool"})
                    continue
                latency = round((time.time() - t_tool) * 1000)
                results.append({
                    "tool": tool,
                    "status": resp.status_code,
                    "latency_ms": latency,
                    "endpoint": str(resp.url),
                    "error": "" if resp.status_code < 400 else f"HTTP {resp.status_code}"
                })
        except Exception as e:
            latency = round((time.time() - t_tool) * 1000)
            results.append({"tool": tool, "status": 502, "latency_ms": latency, "error": str(e)[:100]})

    return {"results": results, "elapsed_ms": round((time.time() - t0) * 1000)}

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
