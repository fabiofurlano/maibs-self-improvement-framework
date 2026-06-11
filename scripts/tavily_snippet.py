"""
Tavily snippet wrapper for MAIBS solve_with_memory.

RWT scope only. Returns a compact WEB CONTEXT block (markdown, hard-capped at
~600 tokens) to inject before Attempt 1. On ANY failure (no key, timeout,
non-2xx, empty results, score filter kills everything) returns "".

Hard rules (locked):
  - search_depth = "basic"
  - max_results = 5
  - query length <= 400 chars
  - filter score > 0.7, take top 2 URLs
  - extract_depth = "basic", format = "markdown", chunks-per-source = 2
  - final snippet hard-capped at ~600 tokens (1 token ~= 4 chars)
  - never raises, never logs the key, never returns raw error to the caller
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional

import httpx

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"

# Hard caps from the locked design doc.
_MAX_QUERY_CHARS = 400
_MIN_SCORE = 0.7
_MAX_URLS = 2
_CHUNKS_PER_SOURCE = 2
_MAX_SNIPPET_CHARS = (600 * 4) - 16  # ~600 tokens at 4 chars/token, minus the "\n[...truncated]" trailer
_HTTP_TIMEOUT_S = 12.0


def _load_api_key() -> Optional[str]:
    """Resolve the Tavily key from env or ~/.hermes/.env. Never logs the value."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.expanduser("~/.hermes/.env")
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == "TAVILY_API_KEY":
                    value = value.strip().strip('"').strip("'")
                    if value:
                        return value
    except OSError:
        return None
    return None


def _truncate_query(prompt: str) -> str:
    """Drop the prompt to a search-friendly query string and cap at _MAX_QUERY_CHARS."""
    q = re.sub(r"\s+", " ", prompt).strip()
    if len(q) > _MAX_QUERY_CHARS:
        q = q[:_MAX_QUERY_CHARS].rsplit(" ", 1)[0] or q[:_MAX_QUERY_CHARS]
    return q


def _cap_snippet(text: str) -> str:
    """Hard-cap the assembled snippet at ~600 tokens. Truncate on a line boundary."""
    if len(text) <= _MAX_SNIPPET_CHARS:
        return text
    cut = text[:_MAX_SNIPPET_CHARS]
    last_nl = cut.rfind("\n")
    if last_nl > _MAX_SNIPPET_CHARS * 0.6:
        cut = cut[:last_nl]
    return cut + "\n[...truncated]"


def get_snippet(prompt: str, *, timeout_s: float = _HTTP_TIMEOUT_S) -> str:
    """
    Run Tavily search+extract for `prompt` and return a compact WEB CONTEXT
    block. Returns "" on any failure path. Never raises.
    """
    if not prompt or not prompt.strip():
        return ""

    api_key = _load_api_key()
    if not api_key:
        return ""

    query = _truncate_query(prompt)
    if not query:
        return ""

    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            # 1) search
            search_resp = client.post(
                TAVILY_SEARCH_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                    "include_answer": False,
                    "include_raw_content": False,
                },
                headers={"Content-Type": "application/json"},
            )
            if search_resp.status_code != 200:
                return ""
            search_payload = search_resp.json()
    except Exception:
        return ""

    results = (search_payload.get("results") or [])
    if not results:
        return ""

    # 2) filter by score, take top N
    picked = [r for r in results if (r.get("score") or 0.0) > _MIN_SCORE][:_MAX_URLS]
    if not picked:
        return ""

    urls = [r.get("url") for r in picked if r.get("url")]
    if not urls:
        return ""

    # 3) extract markdown from those URLs
    try:
        with httpx.Client(timeout=timeout_s) as client:
            extract_resp = client.post(
                TAVILY_EXTRACT_URL,
                json={
                    "api_key": api_key,
                    "urls": urls,
                    "format": "markdown",
                    "extract_depth": "basic",
                    "chunks_per_source": _CHUNKS_PER_SOURCE,
                },
                headers={"Content-Type": "application/json"},
            )
            if extract_resp.status_code != 200:
                return ""
            extract_payload = extract_resp.json()
    except Exception:
        return ""

    extracted = extract_payload.get("results") or []
    if not extracted:
        return ""

    # 4) assemble the WEB CONTEXT block
    lines = ["## WEB CONTEXT (Tavily)", ""]
    for r in picked:
        title = (r.get("title") or "").strip() or "(untitled)"
        url = r.get("url") or ""
        lines.append(f"### {title}")
        lines.append(f"Source: {url}")
        # find the matching extract row by url
        body = ""
        for x in extracted:
            if x.get("url") == url and x.get("raw_content"):
                body = x["raw_content"]
                break
        if not body:
            # search-result content (shorter summary)
            body = (r.get("content") or "").strip()
        if body:
            lines.append("")
            lines.append(body.strip())
        lines.append("")

    snippet = "\n".join(lines).strip()
    snippet = _cap_snippet(snippet)

    return snippet


__all__ = ["get_snippet"]
