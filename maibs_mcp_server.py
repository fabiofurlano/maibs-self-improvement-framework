#!/usr/bin/env python3.10
"""
MAIBS MCP Server — exposes the self-improvement pipeline as a callable tool.

Pipeline (single-step): classify → safety-gate → memory-recall → solve → oracle → evaluate → compress → verdict → memory-write
Pipeline (multi-step):  classify → safety-gate → plan(cloud) → FOR each step: memory-recall → executor(Gemma) → oracle → evaluator → compress → next step

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
    from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
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
LLAMA_URL = "https://pumps-cash-suites-november.trycloudflare.com/v1/chat/completions"
LLAMA_MODEL = "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"

# Lazy import so server starts without it
import requests as _requests

# ═══════════════════════════════════════════════════════
#  PIPELINE INSTRUMENTATION — JSONL logger
# ═══════════════════════════════════════════════════════
PIPELINE_LOG_DIR = Path("/tmp/maibs-self-improvement-framework/logs")
PIPELINE_LOG_DIR.mkdir(parents=True, exist_ok=True)
_pipeline_log_path = None
_pipeline_run_id = None

def _pipeline_log_init(run_id: str = None):
    """Start a new pipeline log file. Call at beginning of solve_multistep."""
    global _pipeline_log_path, _pipeline_run_id
    _pipeline_run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    _pipeline_log_path = PIPELINE_LOG_DIR / f"pipeline-{_pipeline_run_id}.jsonl"
    # Write header metadata
    with open(_pipeline_log_path, "w") as f:
        f.write(json.dumps({
            "event": "run_start",
            "run_id": _pipeline_run_id,
            "timestamp": datetime.now().isoformat(),
        }) + "\n")

def _pipeline_log(event: str, **kwargs):
    """Append a structured log line. Thread-safe enough for single-worker asyncio."""
    global _pipeline_log_path, _pipeline_run_id
    if _pipeline_log_path is None:
        return  # Logging not initialized
    entry = {
        "ts": datetime.now().isoformat(),
        "run_id": _pipeline_run_id,
        "event": event,
        **kwargs,
    }
    with open(_pipeline_log_path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    # Flush aggressively — we want every line on disk immediately for live-tail
    f.close()

def _pipeline_log_finish(result: dict):
    """Write final summary and close the log."""
    global _pipeline_log_path, _pipeline_run_id
    if _pipeline_log_path is None:
        return
    summary = {
        "event": "run_finish",
        "run_id": _pipeline_run_id,
        "passed": result.get("all_passed", False),
        "total_steps": result.get("total_steps", 0),
        "completed_steps": result.get("completed_steps", 0),
        "elapsed_s": result.get("elapsed_s", 0),
        "path_taken": result.get("path_taken", []),
    }
    with open(_pipeline_log_path, "a") as f:
        f.write(json.dumps(summary, default=str) + "\n")
    # Reset for next run
    _pipeline_log_path = None
    _pipeline_run_id = None

def _llama_available() -> bool:
    try: return _requests.get("http://localhost:8080/health", timeout=2).status_code == 200
    except: return False

def call_gemma(prompt: str, timeout: int = 180, max_tokens: int = 500, tags: dict = None) -> tuple[str, float]:
    """Call local Gemma 4 E4B via llama-server. Returns (output, elapsed_seconds).
    
    tags: optional dict with caller context, e.g. {"step": 3, "iteration": 2, "caller": "solver"}
    These are written to the pipeline JSONL log if logging is active.
    """
    tags = tags or {}
    prompt_len = len(prompt)
    t0 = time.time()
    try:
        r = _requests.post(LLAMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0,
        }, timeout=timeout)
        r.raise_for_status()
        output = r.json()["choices"][0]["message"]["content"]
        elapsed = time.time() - t0
        _pipeline_log("gemma_call", 
            caller=tags.get("caller", "unknown"),
            step=tags.get("step", 0),
            iteration=tags.get("iteration", 0),
            prompt_chars=prompt_len,
            output_chars=len(output),
            elapsed_s=round(elapsed, 2),
            success=True,
        )
        return output, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        _pipeline_log("gemma_call",
            caller=tags.get("caller", "unknown"),
            step=tags.get("step", 0),
            iteration=tags.get("iteration", 0),
            prompt_chars=prompt_len,
            elapsed_s=round(elapsed, 2),
            success=False,
            error=str(e)[:200],
        )
        return f"ERROR: {e}", elapsed

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
    output, _ = call_gemma(prompt, timeout=30,
        tags={"step": 0, "iteration": 0, "caller": "classifier"})
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
    output, _ = call_gemma(prompt, timeout=30,
        tags={"step": 0, "iteration": 0, "caller": "safety_gate"})
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
Check the solution against EVERY criterion. Reply with EXACTLY ONE of these two formats — nothing else:

VERDICT: PASS
or
VERDICT: REJECT
REASON: <one sentence, the SPECIFIC criterion that failed and how>

Do NOT suggest fixes. Do NOT rewrite the solution. Do NOT add commentary. Do NOT explain your reasoning.
Output ONLY the verdict line (and reason line if REJECT). No other text.

CRITICAL: If the solution meets ALL criteria, you MUST return VERDICT: PASS.
If the solution violates ANY single criterion, you MUST return VERDICT: REJECT.
When in doubt, check the code literally against each criterion.

CRITICAL — "OR" means ANY option is valid: When a criterion says "X or Y" (e.g., "returns empty string or None"), BOTH X and Y satisfy the criterion. Do NOT reject one because you prefer the other. If the code does X, it passes. If it does Y, it passes. Read "or" literally."""

def evaluate_output(solution: str, original_criteria: str, tags: dict = None) -> tuple[bool, str]:
    """Check solution compliance against original criteria. Returns (passed, reason).
    Gemma E4B, think:false, fast rejection loop."""
    tags = tags or {}
    prompt = (
        f"{EVALUATOR_SYSTEM}\n\n"
        f"ORIGINAL CRITERIA:\n{original_criteria}\n\n"
        f"PROPOSED SOLUTION:\n```python\n{solution}\n```"
    )
    output, _ = call_gemma(prompt, timeout=60, tags={**tags, "caller": "evaluator"})
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
#  PHASE B: Context Engineer Node
# ═══════════════════════════════════════════════════════
CONTEXT_ENGINEER_SYSTEM = """You are a context engineer. You receive the raw output of a completed step and the goal
of the NEXT step. Produce a compressed context containing ONLY what the next step needs.

Rules:
- KEEP: function signatures with their docstrings, class definitions, imports, file paths, variable names, data schemas
- KEEP: any code that the next step will CALL or REFERENCE
- Drop: logs, errors already resolved, verbose explanations, repeated content, comments that aren't docstrings
- Target: 20-30% of input length
- Output the compressed context only. No preamble, no "Here is the compressed context", no markdown headers.

CRITICAL: If the next step needs to call a function defined in this step, you MUST keep that function's full signature and docstring. The next step cannot call a function it cannot see.

The next step's success depends on you keeping exactly what it needs and nothing else."""

def compress_context(raw_output: str, next_step_goal: str, tags: dict = None) -> str:
    """Goal-aware context compression. Returns compressed string at ~20-30% of input.
    Gemma E4B, think:false. Output is stripped clean — no preamble, no markdown.
    
    The returned string is what gets injected into the next solve step's context.
    """
    tags = tags or {}
    prompt = (
        f"{CONTEXT_ENGINEER_SYSTEM}\n\n"
        f"NEXT STEP GOAL:\n{next_step_goal}\n\n"
        f"RAW OUTPUT:\n{raw_output}"
    )
    output, _ = call_gemma(prompt, timeout=120, tags={**tags, "caller": "compressor"})
    output = output.strip()
    
    # Strip common preamble patterns
    for prefix in ["Here is the compressed context:", "Compressed context:", 
                   "```", "---"]:
        if output.lower().startswith(prefix.lower()):
            output = output[len(prefix):].strip()
    
    # Strip trailing markdown fences
    if output.endswith("```"):
        output = output[:-3].strip()
    
    return output


def _build_integration_manifest(code: str) -> str:
    """Extract structural facts from solved code: full function signatures with docstrings,
    file references, schemas. Returns a compact, never-compressed manifest string
    that gets prepended to every subsequent step's context so coherence survives compression.
    
    Format: [MODULE STATE] with function signatures + docstrings — no LLM involved.
    """
    imports = []
    functions = []  # Now: full signature + docstring, not just name
    files = set()
    schemas = []
    
    lines = code.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        # Import collection
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)
        # Function definitions — capture full signature + docstring
        if stripped.startswith("def ") and "(" in stripped:
            sig = stripped  # The def line
            doc_lines = []
            j = i + 1
            # Collect docstring (triple-quoted block after def)
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line.startswith('"""') or next_line.startswith("'''"):
                    doc_lines.append(next_line)
                    # If it's a single-line docstring
                    if next_line.count('"""') >= 2 or next_line.count("'''") >= 2:
                        break
                    # Multi-line: collect until closing triple-quote
                    j += 1
                    while j < len(lines):
                        doc_lines.append(lines[j].strip())
                        if '"""' in lines[j] or "'''" in lines[j]:
                            break
                        j += 1
                    break
                elif next_line.startswith("#") or next_line == "":
                    doc_lines.append(next_line)
                    j += 1
                else:
                    break
            functions.append("\n".join([sig] + doc_lines))
            i = j  # Skip past docstring
        # File operations
        if "open(" in stripped and ('"w"' in stripped or "'w'" in stripped or '"a"' in stripped or "'a'" in stripped):
            m = re.search(r'open\(["\']([^"\']+)["\']', stripped)
            if m:
                files.add(m.group(1))
        # CSV/Dict/list schemas
        if stripped.startswith("fieldnames") or stripped.startswith("columns"):
            schemas.append(stripped)
        i += 1
    
    parts = ["[MODULE STATE — DO NOT COMPRESS]"]
    if functions:
        parts.append("## Functions (callable by next steps)\n" + "\n\n".join(functions))
    if files:
        parts.append(f"Files created: {', '.join(sorted(files))}")
    if schemas:
        parts.append(f"Schemas: {'; '.join(schemas[:3])}")
    if imports:
        parts.append(f"Key imports: {', '.join(imports[:5])}")
    
    return "\n".join(parts) if len(parts) > 1 else "[MODULE STATE] (no structural facts extracted)"

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
#  PHASE C: Orchestrator Loop — solve_multistep
# ═══════════════════════════════════════════════════════

ORCHESTRATOR_SYSTEM = """You are a task planner. Break a complex task into ordered steps.
Each step must be self-contained and testable.

Return ONLY valid JSON — no preamble, no explanation:
{
  "steps": [
    {
      "goal": "what this step accomplishes",
      "criteria": ["criterion 1", "criterion 2"],
      "context_hint": "what information from previous steps this step needs"
    }
  ]
}

Rules:
- Max 10 steps
- Each step has at least one verifiable criterion
- Steps are ordered — each builds on previous ones
- Criteria are specific and testable (not vague like 'works correctly')
- Each step should complete a meaningful unit of work
- If a step needs data from a previous step, note what in context_hint
- CRITICAL: Criteria must be verifiable from CODE TEXT only. The evaluator reads code — it cannot run pip install, check directories, or execute anything. Write criteria like 'function X is defined', 'import Y is present', 'error handling for Z is in the code'. NEVER write criteria like 'pip install succeeds', 'directory exists', or any runtime verification."""

MAX_STEPS = 10
MAX_ITERATIONS_PER_STEP = 3
SAFE_COMPRESSION_FLOOR = 0.21  # Phase B gate result: never compress below 21%


def _plan_steps(task_description: str) -> tuple[list[dict], str]:
    """One cloud call (DeepSeek V4 Pro via OpenRouter) to break task into steps.
    Criteria stored IMMUTABLY at plan time — never modified, never compressed.

    Returns (steps_list, error_string). Error is empty on success.
    """
    prompt = f"{ORCHESTRATOR_SYSTEM}\n\nTASK: {task_description}"

    try:
        output, elapsed = call_deepseek_raw(prompt)
        # Extract JSON — might be in code block or raw
        json_str = output.strip()
        if "```" in json_str:
            lines = json_str.split("\n")
            in_block = False
            block_lines = []
            for line in lines:
                if line.strip().startswith("```"):
                    if in_block:
                        break
                    in_block = True
                    continue
                if in_block:
                    block_lines.append(line)
            json_str = "\n".join(block_lines)

        plan = json.loads(json_str)
        steps = plan.get("steps", [])

        if not steps:
            return [], "Orchestrator returned no steps"
        if len(steps) > MAX_STEPS:
            steps = steps[:MAX_STEPS]

        # Validate each step has required fields
        for i, step in enumerate(steps):
            if "goal" not in step:
                return [], f"Step {i+1} missing 'goal'"
            if "criteria" not in step or not step["criteria"]:
                return [], f"Step {i+1} missing 'criteria'"
            # Ensure criteria is a list
            if isinstance(step["criteria"], str):
                step["criteria"] = [step["criteria"]]

        return steps, ""
    except json.JSONDecodeError as e:
        return [], f"Orchestrator JSON parse error: {str(e)[:200]}"
    except Exception as e:
        return [], f"Orchestrator error: {str(e)[:200]}"


def _execute_step(step: dict, task_description: str, previous_context: str,
                  step_index: int, total_steps: int,
                  integration_manifest: str = "") -> dict:
    """Execute one step: memory-recall → executor(Gemma) → oracle → evaluator → compress.

    Max 3 iterations per step. Third rejection triggers DeepSeek reasoning lifeline.
    integration_manifest: cumulative structural facts from previous steps (never compressed).
    Returns: {goal, solution, passed, evaluator_passed, evaluator_reason,
              compressed_context, context_size, integration_manifest, logs}
    """
    logs = []
    goal = step["goal"]
    criteria_list = step.get("criteria", [])
    # Store criteria IMMUTABLY — pass original list to evaluator every time
    criteria_text = "\n".join(f"- {c}" for c in criteria_list)

    # ── Build context for this step ─────────────────
    context_parts = []
    if previous_context and len(previous_context.strip()) > 10:
        context_parts.append(
            f"## Context from previous steps (compressed)\n{previous_context}"
        )
    # Integration manifest: structural facts never compressed, always visible
    if integration_manifest and len(integration_manifest.strip()) > 20:
        context_parts.insert(0, 
            f"## Integration Manifest (CUMULATIVE — DO NOT REMOVE)\n{integration_manifest}"
        )

    # Memory recall: search experience index
    entries = read_experience_index()
    if entries:
        exp_context = filter_experiences(entries, "coding")
        if exp_context:
            context_parts.append(exp_context[:600])

    # Tavily snippet injection
    snippet = _tavily_snippet(goal)
    if snippet:
        context_parts.append(snippet)

    context_str = "\n\n".join(context_parts)
    context_size = len(context_str)
    logs.append(f"context_size:{context_size}")

    if context_size > 4000:
        logs.append(f"WARNING:context_over_4K({context_size})")
        context_str = context_str[:4000]
        logs.append("context_truncated_to_4000")

    # ── Build base step prompt (used for retries) ──
    def _build_step_prompt(extra: str = "") -> str:
        parts = [context_str]
        if extra:
            parts.append(extra)
        return "\n\n".join(parts) + f"""

## Current Step ({step_index + 1}/{total_steps})
Goal: {goal}

Success criteria (MUST satisfy ALL):
{criteria_text}

Write Python code that completes this step. Return ONLY the code in a markdown code block.
Include comments showing which criteria you satisfy.
"""

    # ── Execute loop — max 3 iterations ────────────
    solution = ""
    passed = False
    evaluator_passed = False
    evaluator_reason = ""
    all_attempt_errors = []
    step_t0 = time.time()
    PER_STEP_TIMEOUT = 600  # 10 minute hard cap per step

    for iteration in range(1, MAX_ITERATIONS_PER_STEP + 1):
        # Circuit breaker: step timeout
        step_elapsed = time.time() - step_t0
        if step_elapsed > PER_STEP_TIMEOUT:
            evaluator_reason = f"Step timeout after {step_elapsed:.0f}s"
            logs.append(f"CIRCUIT_BREAK:timeout({step_elapsed:.0f}s)")
            _pipeline_log("circuit_break", breaker="step_timeout",
                step=step_index+1, elapsed_s=round(step_elapsed,1))
            break

        logs.append(f"iter_{iteration}")

        step_prompt = _build_step_prompt()
        if iteration > 1:
            error_desc = evaluator_reason or (all_attempt_errors[-1] if all_attempt_errors else 'unknown')
            failure_note = f"""## YOUR PREVIOUS ATTEMPT FAILED
Error: {error_desc[:200]}

**Write a correct solution that meets ALL criteria.**"""

            # ── Escalation ladder: memory → web search → lifeline ──
            if iteration == 2:
                # Layer 1: Memory recall — search for similar past fixes
                entries = read_experience_index()
                if entries:
                    exp_context = filter_experiences(entries, "coding")
                    if exp_context:
                        failure_note += f"\n\n## PAST EXPERIENCE (similar tasks)\n{exp_context[:500]}"
                        logs.append("retry:memory_injected")
                        _pipeline_log("retry:memory_injected", step=step_index+1, iteration=iteration,
                            context_chars=len(exp_context[:500]))
                else:
                    logs.append("retry:memory_empty")
                    _pipeline_log("retry:memory_empty", step=step_index+1, iteration=iteration)
            elif iteration == 3:
                # Layer 2: Tavily web search for the specific error
                web_query = f"{goal} - fixing error: {error_desc[:100]}"
                snippet = _tavily_snippet(web_query)
                if snippet:
                    failure_note += f"\n\n## WEB SEARCH RESULTS\n{snippet}"
                    logs.append("retry:tavily_injected")
                    _pipeline_log("retry:tavily_injected", step=step_index+1, iteration=iteration,
                        context_chars=len(snippet))
                else:
                    logs.append("retry:tavily_empty")
                    _pipeline_log("retry:tavily_empty", step=step_index+1, iteration=iteration)

            step_prompt = _build_step_prompt(failure_note)

        output, elapsed = call_gemma(step_prompt, timeout=180, max_tokens=500,
            tags={"step": step_index + 1, "iteration": iteration, "caller": "solver"})
        code = extract_code(output)
        logs.append(f"gemma:{elapsed:.1f}s")

        # Oracle: catch syntax/runtime errors
        oracle_passed, oracle_error = run_oracle(code, "", [])
        if oracle_error:
            all_attempt_errors.append(oracle_error)
            logs.append(f"oracle_err:{oracle_error[:80]}")
            solution = code  # Save for retry injection
            if iteration == MAX_ITERATIONS_PER_STEP:
                evaluator_reason = f"Code error after {MAX_ITERATIONS_PER_STEP} iterations: {oracle_error}"
            continue

        # Evaluator: check criteria compliance (immutable original criteria)
        ev_passed, ev_reason = evaluate_output(code, criteria_text,
            tags={"step": step_index + 1, "iteration": iteration, "caller": "evaluator"})
        evaluator_passed = ev_passed
        evaluator_reason = ev_reason

        if ev_passed:
            solution = code
            passed = True
            logs.append("evaluator:PASS")
            break
        else:
            solution = code  # Save for retry injection
            logs.append(f"evaluator:REJECT ({ev_reason[:80]})")

    # ── Exhausted 3 iterations — reasoning lifeline ─
    if not passed:
        logs.append("reasoning_lifeline")
        _pipeline_log("reasoning_lifeline", step=step_index+1,
            num_errors=len(all_attempt_errors),
            evaluator_reason=evaluator_reason[:200])

        # Build lifeline prompt with ALL failure context
        error_summary = evaluator_reason
        if all_attempt_errors:
            error_summary = f"All {len(all_attempt_errors)} attempts failed. "
            if evaluator_reason and evaluator_reason != error_summary:
                error_summary += evaluator_reason
            else:
                error_summary += f"Last error: {all_attempt_errors[-1][:150]}"

        lifeline_prompt = (
            f"Task step: {goal}\n"
            f"Criteria:\n{criteria_text}\n\n"
            f"The weaker model failed {MAX_ITERATIONS_PER_STEP} times.\n"
            f"Latest attempt:\n```python\n{solution[:500]}\n```\n"
            f"Error: {error_summary}\n\n"
            f"Provide the CORRECT solution as a Python code block. "
            f"Focus on meeting EVERY criterion listed above."
        )
        reasoning = call_deepseek(
            f"Step: {goal}\nCriteria: {criteria_text}",
            [{"code": solution[:500], "error": evaluator_reason}]
        )

        step_prompt = _build_step_prompt(f"""## EXPERT REASONING (DeepSeek V4 Pro)
{reasoning[:1000]}

Use this expert analysis to write the CORRECT solution.""")
        output, elapsed = call_gemma(step_prompt, timeout=180, max_tokens=1500,
            tags={"step": step_index + 1, "iteration": 0, "caller": "lifeline_solver"})
        code = extract_code(output)
        logs.append(f"lifeline_gemma:{elapsed:.1f}s")

        # Final evaluator check
        ev_passed, ev_reason = evaluate_output(code, criteria_text,
            tags={"step": step_index + 1, "iteration": 0, "caller": "lifeline_evaluator"})
        evaluator_passed = ev_passed
        evaluator_reason = ev_reason

        if ev_passed:
            solution = code
            passed = True
            logs.append("lifeline:PASS")
        else:
            logs.append(f"lifeline:FAIL ({ev_reason[:80]})")
            # Partial result + flag
            evaluator_reason = f"Failed after reasoning lifeline: {ev_reason}"

    # ── Compress context for next step (Phase B) ───
    compressed = ""
    step_manifest = ""
    if solution and passed:
        compressed = compress_context(solution, goal,
            tags={"step": step_index + 1, "iteration": 0, "caller": "compressor"})
        comp_ratio = len(compressed) / max(len(solution), 1)
        logs.append(f"comp_ratio:{comp_ratio:.2f}")
        # Build integration manifest from solved code
        step_manifest = _build_integration_manifest(solution)
        logs.append(f"manifest_size:{len(step_manifest)}")

        # Safe floor guard (Phase B: 21%)
        if comp_ratio < SAFE_COMPRESSION_FLOOR:
            logs.append(
                f"WARNING:comp_below_21%_floor({comp_ratio:.2f})"
            )
            # Fall back to using the solution with a size cap instead
            compressed = solution[:int(len(solution) * SAFE_COMPRESSION_FLOOR * 2)]
            logs.append(f"floor_capped:{len(compressed)}chars")

    return {
        "goal": goal,
        "solution": solution[:2000],
        "passed": passed,
        "evaluator_passed": evaluator_passed,
        "evaluator_reason": evaluator_reason,
        "compressed_context": compressed[:2000],
        "context_size": context_size,
        "integration_manifest": step_manifest,
        "logs": logs,
    }


def solve_multistep(task_description: str, task_type: str = "coding",
                    original_criteria: str = "") -> dict:
    """Orchestrate a multi-step task through the full pipeline.

    ONE cloud call (DeepSeek V4 Pro) to plan steps.
    Gemma E4B executes every step locally: memory-recall → executor → oracle →
    evaluator → compress → next step.

    Criteria stored IMMUTABLY at plan time — never modified, never compressed.
    Hard caps: max 3 iterations per step, max 10 steps per task.
    think: false on every local call.
    
    original_criteria: 6-criteria task rubric. Used for final product evaluation
    after all steps complete (Phase D fix #2). 
    """
    run_t0 = time.time()
    _pipeline_log_init()
    _pipeline_log("pipeline_start", task=task_description[:200])
    
    path_taken = []
    step_results = []

    # ── Phase 7.5: Intent Classifier ───────────────
    _pipeline_log("phase", name="classify_intent")
    intent = classify_intent(task_description)
    path_taken.append(f"intent:{intent}")

    if intent == "clarify":
        _pipeline_log("pipeline_abort", reason="intent_clarify")
        return {
            "solution": "", "passed": False,
            "error": "Task needs clarification. Provide more detail.",
            "path_taken": path_taken, "steps": [],
            "total_steps": 0, "completed_steps": 0, "failed_steps": [], "elapsed_s": time.time()-run_t0,
        }

    # ── Phase 7.5: Safety Gate ─────────────────────
    _pipeline_log("phase", name="safety_gate")
    go, block_reason = safety_gate(task_description)
    if not go:
        _pipeline_log("pipeline_abort", reason=f"safety_gate_blocked:{block_reason}")
        return {
            "solution": "", "passed": False,
            "error": f"Safety gate blocked: {block_reason}",
            "path_taken": path_taken, "steps": [],
            "total_steps": 0, "completed_steps": 0, "failed_steps": [], "elapsed_s": time.time()-run_t0,
        }
    path_taken.append("safety_gate:GO")

    # ── Orchestrator: Plan steps (ONE cloud call) ──
    _pipeline_log("phase", name="orchestrator_planning")
    path_taken.append("orchestrator_planning")
    steps, plan_error = _plan_steps(task_description)

    if plan_error:
        _pipeline_log("pipeline_abort", reason=f"planning_failed:{plan_error}")
        return {
            "solution": "", "passed": False,
            "error": f"Planning failed: {plan_error}",
            "path_taken": path_taken, "steps": [],
            "total_steps": 0, "completed_steps": 0, "failed_steps": [], "elapsed_s": time.time()-run_t0,
        }

    path_taken.append(f"planned_{len(steps)}_steps")
    _pipeline_log("plan_complete", num_steps=len(steps))
    
    # Log planned step goals for traceability
    for i, s in enumerate(steps):
        _pipeline_log("step_planned", step=i+1, goal=s.get("goal","")[:120])

    # ── Execute each step ──────────────────────────
    previous_context = ""
    all_passed = True
    failed_steps = []
    cumulative_manifest = ""
    manifest_sizes = []

    for i, step in enumerate(steps):
        step_t0 = time.time()
        _pipeline_log("step_start", step=i+1, total_steps=len(steps), 
                       goal=step["goal"][:120])
        
        result = _execute_step(
            step, task_description, previous_context, i, len(steps),
            integration_manifest=cumulative_manifest
        )
        step_elapsed = time.time() - step_t0
        step_results.append(result)
        
        if result.get("integration_manifest"):
            manifest_sizes.append(len(result["integration_manifest"]))

        _pipeline_log("step_end", 
            step=i+1, 
            passed=result["passed"],
            elapsed_s=round(step_elapsed, 1),
            calls=len([l for l in result.get("logs",[]) if "gemma:" in l]),
            evaluator_passed=result.get("evaluator_passed"),
            evaluator_reason=(result.get("evaluator_reason","")[:120]),
            context_size=result.get("context_size", 0),
        )

        if result["passed"]:
            path_taken.append(f"step_{i+1}_pass")
            previous_context = result["compressed_context"]
            if result.get("integration_manifest"):
                if cumulative_manifest:
                    cumulative_manifest += "\n" + result["integration_manifest"]
                else:
                    cumulative_manifest = result["integration_manifest"]
        else:
            path_taken.append(f"step_{i+1}_fail")
            all_passed = False
            failed_steps.append({
                "step": i + 1,
                "goal": step["goal"],
                "criteria": step.get("criteria", []),
                "reason": result["evaluator_reason"],
            })
            _pipeline_log("pipeline_break", reason=f"step_{i+1}_failed", 
                          step=i+1, evaluator_reason=result.get("evaluator_reason","")[:200])
            break

    # ── Assemble final result ──────────────────────
    final_solution = "\n\n".join([
        f"## Step {i + 1}: {r['goal']}\n```python\n{r['solution']}\n```"
        for i, r in enumerate(step_results) if r["solution"]
    ])

    # ── Final Product Evaluation (Phase D fix #2) ───────
    final_eval = {}
    if all_passed and final_solution.strip() and original_criteria.strip():
        _pipeline_log("phase", name="final_product_eval")
        path_taken.append("final_product_eval")
        ev_passed, ev_reason = evaluate_output(final_solution, original_criteria,
            tags={"step": -1, "iteration": 0, "caller": "final_evaluator"})
        final_eval = {"passed": ev_passed, "reason": ev_reason}
        if ev_passed:
            path_taken.append("final_eval:PASS")
            _pipeline_log("final_eval", passed=True)
        else:
            path_taken.append(f"final_eval:REJECT")
            all_passed = False
            _pipeline_log("final_eval", passed=False, reason=ev_reason[:200])

    # ── Write to experience DB ─────────────────────
    if all_passed and final_solution.strip():
        try:
            completed = sum(1 for r in step_results if r["passed"])
            _write_success(task_description, final_solution,
                          completed, path_taken)
        except Exception as e:
            path_taken.append(f"db_write:{e}")

    total_elapsed = time.time() - run_t0
    completed = sum(1 for r in step_results if r.get("passed"))
    
    result = {
        "solution": final_solution[:5000],
        "passed": all_passed,
        "path_taken": path_taken,
        "steps": [{"step": i+1, "goal": r["goal"], "passed": r["passed"], 
                    "evaluator_reason": r.get("evaluator_reason",""),
                    "context_size": r.get("context_size",0)}
                  for i, r in enumerate(step_results)],
        "total_steps": len(steps),
        "completed_steps": completed,
        "failed_steps": failed_steps,
        "final_product_eval": final_eval,
        "manifest_sizes": manifest_sizes,
        "elapsed_s": round(total_elapsed, 1),
    }
    
    _pipeline_log_finish(result)
    return result

# ═══════════════════════════════════════════════════════
#  FastAPI / JSON-RPC endpoints
# ═══════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "server": "MAIBS MCP Server",
        "version": "1.0.0",
        "tools": ["solve_with_memory", "solve_multistep"],
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
            },
            {
                "name": "solve_multistep",
                "description": "Orchestrate a multi-step task through the full pipeline. ONE cloud call (DeepSeek V4 Pro) plans the steps with immutable criteria. Gemma E4B executes each step: memory-recall → executor → oracle → evaluator → compress → next step. Hard caps: 3 iterations per step, 10 steps per task.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_description"],
                    "properties": {
                        "task_description": {
                            "type": "string",
                            "description": "The complex multi-step task description"
                        },
                        "task_type": {
                            "type": "string",
                            "description": "Task category for experience index filtering: coding, general, benchmark",
                            "default": "coding"
                        },
                        "original_criteria": {
                            "type": "string",
                            "description": "Original task rubric (e.g., 6 binary criteria). Used for final product evaluation after all steps complete (Phase D fix #2)."
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
        
        if tool_name == "solve_multistep":
            task_desc = arguments.get("task_description", "")
            if not task_desc:
                return rpc_result(error={"code": -32602, "message": "task_description is required"})
            
            task_type = arguments.get("task_type", "coding")
            original_criteria = arguments.get("original_criteria", "")
            
            result = solve_multistep(task_desc, task_type, original_criteria)
            
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
#  Pipeline Inspector API — read JSONL logs
# ═══════════════════════════════════════════════════════
LOGS_DIR = REPO_DIR / "logs"

@app.get("/api/logs")
async def list_logs(request: Request):
    """List available pipeline log files."""
    check_auth(request)
    if not LOGS_DIR.exists():
        return []
    files = sorted([f.name for f in LOGS_DIR.glob("pipeline-*.jsonl")], reverse=True)
    return files

@app.get("/api/logs/{filename}")
async def get_log(request: Request, filename: str):
    """Read a pipeline log file as JSON array."""
    check_auth(request)
    filepath = LOGS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    events = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"raw": line[:500]})
    return events

@app.get("/inspector")
async def pipeline_inspector(request: Request):
    """Serve the pipeline inspector HTML page."""
    inspector_path = REPO_DIR / "dashboard" / "pipeline-inspector.html"
    if not inspector_path.exists():
        raise HTTPException(status_code=404, detail="Inspector not found")
    return HTMLResponse(content=inspector_path.read_text())

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
