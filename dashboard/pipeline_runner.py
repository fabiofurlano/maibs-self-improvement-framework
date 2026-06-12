"""
MAIBS Pipeline Runner — Streamlit UI
Type a task, set criteria, click Run, watch the pipeline work.
"""
import streamlit as st
import json
import urllib.request
import time
import os

MCP_URL = os.environ.get("MAIBS_MCP_URL", "http://localhost:8282")
st.set_page_config(page_title="MAIBS Pipeline", page_icon="🔬", layout="wide")

st.markdown("""
<style>
    .pass { color: #3fb950; font-weight: bold; }
    .fail { color: #f85149; font-weight: bold; }
    .tool-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; margin: 2px; }
    .tool-memory { background: #1a2a3a; color: #58a6ff; }
    .tool-tavily { background: #2a1a3a; color: #bc8cff; }
    .tool-lifeline { background: #3a2a1a; color: #d2991d; }
    .tool-eval { background: #1a3a1a; color: #3fb950; }
    .tool-compress { background: #1a1a2a; color: #79c0ff; }
    .step-card { border-left: 4px solid #30363d; padding: 8px 16px; margin: 8px 0; border-radius: 4px; background: #161b22; }
    .step-pass { border-left-color: #3fb950; }
    .step-fail { border-left-color: #f85149; }
    pre { background: #0d1117; padding: 12px; border-radius: 6px; font-size: 0.85em; max-height: 300px; overflow-y: auto; }
</style>
""", unsafe_allow_html=True)

st.title("🔬 MAIBS Pipeline Runner")
st.caption("Type a task, set criteria, and watch the pipeline run step by step.")

# ── Server check ───────────────────────────────────────
try:
    resp = urllib.request.urlopen(f"{MCP_URL}/health", timeout=3)
    health = json.loads(resp.read().decode())
    st.success(f"✅ MCP Server online — v{health.get('version','?')} — {MCP_URL}")
except Exception as e:
    st.error(f"❌ MCP Server offline: {e}")
    st.stop()

# ── Input section (main area, not sidebar) ─────────────
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📋 Task")
    task = st.text_area(
        "What should the pipeline do?",
        value="Compare the current pricing of three cloud GPU providers (Vast.ai, RunPod, Lambda Labs) for renting an NVIDIA A100 80GB GPU. Include: hourly price for each, minimum rental duration, and which is cheapest. Format as a markdown comparison table.",
        height=120,
        label_visibility="collapsed",
    )

with col2:
    st.subheader("✅ Criteria")
    criteria_text = st.text_area(
        "One per line — what must the output include?",
        value="Names all three providers: Vast.ai, RunPod, Lambda Labs\nIncludes hourly price for each provider (specific dollar amount)\nIncludes minimum rental duration for each\nIdentifies which provider is cheapest\nOutput is formatted as a markdown table\nPrices are current (2025-2026), not outdated training data",
        height=120,
        label_visibility="collapsed",
    )

col3, col4, col5 = st.columns([1, 1, 2])
with col3:
    timeout = st.number_input("⏱️ Timeout (seconds)", min_value=30, max_value=600, value=300, step=30)
with col4:
    st.write("")  # spacer
    st.write("")
    run_btn = st.button("▶️ Run Pipeline", type="primary", use_container_width=True)

st.divider()

# ── Run logic ──────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "running" not in st.session_state:
    st.session_state.running = False

if run_btn and not st.session_state.running:
    st.session_state.running = True
    st.session_state.results = None
    
    criteria = [c.strip() for c in criteria_text.strip().split("\n") if c.strip()]
    
    if not task.strip():
        st.error("Please enter a task description.")
        st.session_state.running = False
    elif len(criteria) < 2:
        st.error("Please enter at least 2 criteria.")
        st.session_state.running = False
    else:
        status_area = st.empty()
        status_area.info(f"⏳ Running pipeline... (timeout: {timeout}s)")
        
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "solve_multistep",
                "arguments": {
                    "task_description": task.strip(),
                    "criteria": criteria,
                }
            }
        })
        
        t0 = time.time()
        try:
            req = urllib.request.Request(
                f"{MCP_URL}/mcp",
                data=body.encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            result = json.loads(resp.read().decode())
            elapsed = time.time() - t0
            
            content = result.get("result", {}).get("content", [{}])
            text = content[0].get("text", "") if content else ""
            
            st.session_state.results = {
                "raw": text,
                "elapsed": elapsed,
                "result": result,
            }
            status_area.empty()
        except Exception as e:
            st.session_state.results = {"error": str(e), "elapsed": time.time() - t0}
            status_area.empty()
        
        st.session_state.running = False
        st.rerun()

# ── Display Results ────────────────────────────────────
results = st.session_state.results
if results:
    if "error" in results:
        st.error(f"❌ Pipeline failed: {results['error']} ({results['elapsed']:.0f}s)")
    else:
        text = results["raw"]
        elapsed = results["elapsed"]
        
        # Parse key metrics
        import re
        
        total_steps = 0
        completed = 0
        passed = False
        path = []
        steps_data = []
        
        # Extract from text
        ts_match = re.search(r'"total_steps":\s*(\d+)', text)
        cs_match = re.search(r'"completed_steps":\s*(\d+)', text)
        ps_match = re.search(r'"passed":\s*(true|false)', text)
        
        if ts_match: total_steps = int(ts_match.group(1))
        if cs_match: completed = int(cs_match.group(1))
        if ps_match: passed = ps_match.group(1) == "true"
        
        # Extract path
        path_match = re.search(r'"path_taken":\s*\[(.*?)\]', text, re.DOTALL)
        if path_match:
            path_raw = path_match.group(1)
            path = [p.strip().strip('"') for p in path_raw.split(",")]
        
        # Extract steps
        step_blocks = re.findall(r'"step":\s*(\d+).*?"passed":\s*(true|false).*?"goal":\s*"([^"]{5,80})"', text)
        for s_num, s_pass, s_goal in step_blocks:
            steps_data.append({
                "step": int(s_num),
                "passed": s_pass == "true",
                "goal": s_goal,
            })
        
        # Summary bar
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📊 Total Steps", total_steps or "?")
        c2.metric("✅ Completed", completed or "?")
        c3.metric("⏱️ Elapsed", f"{elapsed:.0f}s")
        c4.metric("🏁 Result", "✅ PASS" if passed else "❌ FAIL" if total_steps > 0 else "⏳")
        
        # Path visualization
        if path:
            st.markdown("### 🔗 Path Taken")
            path_html = " → ".join([
                f'<span style="color:#3fb950">{p}</span>' if "pass" in p.lower() 
                else f'<span style="color:#f85149">{p}</span>' if "fail" in p.lower()
                else f'<span style="color:#8b949e">{p}</span>'
                for p in path
            ])
            st.markdown(path_html, unsafe_allow_html=True)
        
        # Step cards
        if steps_data:
            st.markdown("### 📝 Steps")
            for s in steps_data:
                cls = "step-pass" if s["passed"] else "step-fail"
                icon = "✅" if s["passed"] else "❌"
                st.markdown(f"""
                <div class="step-card {cls}">
                    <strong>{icon} Step {s['step']}</strong>: {s['goal']}
                </div>
                """, unsafe_allow_html=True)
        
        st.divider()
        
        # Full output
        with st.expander("📄 Full Pipeline Output", expanded=False):
            st.code(text[:15000], language="text")
        
        # Raw JSON
        with st.expander("🔧 Raw MCP Response", expanded=False):
            st.json(results["result"])

# ── Footer ─────────────────────────────────────────────
st.divider()
st.caption(f"MAIBS Pipeline Runner — MCP: {MCP_URL} — Logs: /tmp/maibs-self-improvement-framework/logs/")
