#!/usr/bin/env python3
"""Stage 2 Oracle — MBPP format.
Reads task from JSON file, extracts agent's code from solve output,
runs MBPP test assertions, writes PASS/FAIL to /tmp/sil-oracle-result.txt.

MBPP test format:
  - test_setup_code: imports/setup (optional)
  - test_list: list of assert statements
  - No check() function — assertions run directly

Usage: python3 oracle-runner.py <task_json_path> <solve_output_path>
"""
import json, os, sys

TASK_FILE = sys.argv[1]
SOLVE_OUTPUT_FILE = sys.argv[2]
RESULT_FILE = "/tmp/sil-oracle-result.txt"

# Load task
task = json.load(open(TASK_FILE))
test_setup = task.get("test_setup_code", "")
test_list = task["test_list"]

# Read solve output
solve_output = open(SOLVE_OUTPUT_FILE).read()

# Extract code — handle markdown code blocks and raw code
lines = solve_output.split("\n")
agent_lines = []
in_block = False
block_count = 0

for line in lines:
    stripped = line.strip()
    if stripped.startswith("```"):
        if in_block:
            block_count += 1
            in_block = False
            continue
        else:
            in_block = True
            block_count += 1
            continue
    if in_block:
        agent_lines.append(line)

# If no code block found, try raw code
if not agent_lines:
    # Use everything after the first non-comment Python-looking line
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("//") and not s.startswith("Here"):
            if "def " in s or "import " in s or s.startswith("class ") or s.startswith("from "):
                agent_lines.append(line)
            elif agent_lines:  # keep going once we start
                agent_lines.append(line)

agent_code = "\n".join(agent_lines) if agent_lines else solve_output

# Run oracle
full_code = test_setup + "\n" + agent_code + "\n"
full_code += "\n".join(test_list)

try:
    exec(full_code, {})
    verdict = "PASS"
    error_msg = ""
except AssertionError as e:
    verdict = "FAIL"
    error_msg = f"AssertionError: {e}"
except SyntaxError as e:
    verdict = "FAIL"
    error_msg = f"SyntaxError: {e}"
except Exception as e:
    verdict = "FAIL"
    error_msg = f"{type(e).__name__}: {e}"

# Write result
with open(RESULT_FILE, "w") as f:
    f.write(f"ORACLE_{verdict}")
    if error_msg:
        f.write(f"\nError: {error_msg}")

print(f"ORACLE_{verdict}")
if error_msg:
    print(f"  {error_msg}")
