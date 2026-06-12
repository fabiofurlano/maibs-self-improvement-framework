#!/usr/bin/env python3
"""Analyze pipeline JSONL logs into a human-readable summary.

Usage:
  python3 scripts/analyze_pipeline.py [log_file.jsonl]
  
If no log file specified, reads the most recent from logs/ directory.
"""

import json, sys, os
from collections import defaultdict
from pathlib import Path

LOGS_DIR = Path("/tmp/maibs-self-improvement-framework/logs")

def find_latest_log():
    """Find the most recent pipeline log file."""
    logs = sorted(LOGS_DIR.glob("pipeline-*.jsonl"), key=os.path.getmtime, reverse=True)
    if not logs:
        print("❌ No pipeline logs found in", LOGS_DIR)
        sys.exit(1)
    return logs[0]

def analyze(log_path):
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        print("❌ Empty log file")
        return

    # Group by event type
    by_event = defaultdict(list)
    for e in events:
        by_event[e.get("event", "unknown")].append(e)

    print("=" * 70)
    print("PIPELINE RUN SUMMARY")
    print("=" * 70)

    # Run metadata
    run_start = next((e for e in events if e["event"] == "run_start"), {})
    run_finish = next((e for e in events if e["event"] == "run_finish"), {})
    print(f"  Run ID:    {run_start.get('run_id', 'unknown')}")
    print(f"  Started:   {run_start.get('timestamp', 'unknown')}")
    
    if run_finish:
        print(f"  Passed:    {'✅ YES' if run_finish.get('passed') else '❌ NO'}")
        print(f"  Steps:     {run_finish.get('completed_steps',0)}/{run_finish.get('total_steps',0)} completed")
        print(f"  Elapsed:   {run_finish.get('elapsed_s',0):.0f}s ({run_finish.get('elapsed_s',0)/60:.1f}m)")
    else:
        print(f"  Status:    ⚠️  RUN DID NOT FINISH (killed or crashed)")

    # Pipeline phases
    print(f"\n{'─' * 70}")
    print("PIPELINE PHASES")
    print(f"{'─' * 70}")
    
    phases = [e for e in events if e["event"] == "phase"]
    for p in phases:
        print(f"  ▶ {p.get('name', 'unknown')}")

    # Planned steps
    planned = [e for e in events if e["event"] == "step_planned"]
    if planned:
        print(f"\n  📋 {len(planned)} steps planned:")
        for s in planned:
            print(f"     Step {s.get('step')}: {s.get('goal','')[:100]}")

    # Step execution
    print(f"\n{'─' * 70}")
    print("STEP EXECUTION")
    print(f"{'─' * 70}")
    
    step_ends = [e for e in events if e["event"] == "step_end"]
    for se in step_ends:
        status = "✅ PASS" if se.get("passed") else "❌ FAIL"
        print(f"  Step {se.get('step')}: {status} | {se.get('elapsed_s',0):.0f}s | {se.get('calls',0)} gemma calls | ctx={se.get('context_size',0)} chars")
        if se.get("evaluator_reason"):
            print(f"         Reason: {se.get('evaluator_reason','')[:150]}")

    # Circuit breakers
    breakers = [e for e in events if e["event"] == "circuit_break"]
    if breakers:
        print(f"\n{'─' * 70}")
        print("CIRCUIT BREAKERS TRIPPED")
        print(f"{'─' * 70}")
        for cb in breakers:
            print(f"  ⚡ {cb.get('breaker')} at step {cb.get('step')}: {cb.get('last_error', cb.get('elapsed_s',''))}")

    # Call breakdown
    gemma_calls = [e for e in events if e["event"] == "gemma_call"]
    if gemma_calls:
        print(f"\n{'─' * 70}")
        print(f"GEMMA CALL BREAKDOWN ({len(gemma_calls)} total)")
        print(f"{'─' * 70}")
        
        by_caller = defaultdict(lambda: {"count": 0, "total_s": 0, "total_chars_out": 0, "errors": 0})
        for gc in gemma_calls:
            caller = gc.get("caller", "unknown")
            by_caller[caller]["count"] += 1
            by_caller[caller]["total_s"] += gc.get("elapsed_s", 0)
            by_caller[caller]["total_chars_out"] += gc.get("output_chars", 0)
            if not gc.get("success", True):
                by_caller[caller]["errors"] += 1

        print(f"  {'Caller':<20s} {'Count':>6s} {'Total':>8s} {'Avg':>7s} {'Output':>8s} {'Errors':>6s}")
        print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*7} {'-'*8} {'-'*6}")
        
        total_time = 0
        for caller, stats in sorted(by_caller.items(), key=lambda x: -x[1]["total_s"]):
            avg = stats["total_s"] / stats["count"] if stats["count"] else 0
            total_time += stats["total_s"]
            err_str = f"{stats['errors']}" if stats["errors"] > 0 else "-"
            print(f"  {caller:<20s} {stats['count']:>6d} {stats['total_s']:>7.0f}s {avg:>6.1f}s {stats['total_chars_out']:>7d}c {err_str:>6s}")
        
        print(f"  {'─'*55}")
        print(f"  {'TOTAL llama time':>20s} {total_time:>7.0f}s ({total_time/60:.1f}m)")

        # Per-step breakdown
        print(f"\n{'─' * 70}")
        print("PER-STEP CALL DETAIL")
        print(f"{'─' * 70}")
        
        by_step = defaultdict(lambda: defaultdict(list))
        for gc in gemma_calls:
            step = gc.get("step", 0)
            caller = gc.get("caller", "unknown")
            by_step[step][caller].append(gc)

        for step_num in sorted(by_step.keys()):
            callers = by_step[step_num]
            total_calls = sum(len(v) for v in callers.values())
            step_time = sum(gc.get("elapsed_s", 0) for v in callers.values() for gc in v)
            parts = []
            for caller, calls in sorted(callers.items(), key=lambda x: -len(x[1])):
                parts.append(f"{len(calls)} {caller}")
            print(f"  Step {step_num:2d}: {total_calls:2d} calls, {step_time:5.0f}s — {', '.join(parts)}")

    # Pipeline breaks
    breaks = [e for e in events if e["event"] in ("pipeline_break", "pipeline_abort")]
    if breaks:
        print(f"\n{'─' * 70}")
        print("PIPELINE STOP REASON")
        print(f"{'─' * 70}")
        for b in breaks:
            print(f"  {b['event']}: {b.get('reason', 'unknown')}")
            if b.get("evaluator_reason"):
                print(f"         {b['evaluator_reason'][:200]}")

    # Final eval
    final_evals = [e for e in events if e["event"] == "final_eval"]
    for fe in final_evals:
        status = "✅ PASS" if fe.get("passed") else "❌ REJECT"
        print(f"\n  Final product eval: {status}")
        if fe.get("reason"):
            print(f"  {fe['reason'][:200]}")

    print(f"\n{'=' * 70}")
    print("LOG FILE:", log_path)
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        log_path = sys.argv[1]
    else:
        log_path = find_latest_log()
    
    print(f"Reading: {log_path}\n")
    analyze(log_path)
