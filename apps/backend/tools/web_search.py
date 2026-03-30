"""
General-purpose web search tools for the AdvisorAgent.

Three backends are available — pick one via ACTIVE_WEB_SEARCH in advisor_agent.py:
  - tavily      : Tavily Search API  (TAVILY_API_KEY required)
  - duckduckgo  : DuckDuckGo         (no API key, duckduckgo-search package required)
  - serper      : Serper.dev (Google) (SERPER_API_KEY required)

Each function returns a plain-text formatted string ready to be used as a ToolMessage.
"""

from __future__ import annotations

import os
import re

import requests


class WebSearchError(Exception):
    pass


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# ===========================< Tavily >============================

def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Tavily Search API — good general web coverage, returns clean snippets.
    Requires: TAVILY_API_KEY in environment.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise WebSearchError("TAVILY_API_KEY 환경 변수가 설정되지 않았습니다.")

    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    return [
        {
            "title": item.get("title", ""),
            "description": item.get("content", ""),
            "link": item.get("url", ""),
        }
        for item in data.get("results", [])
    ]


# ===========================< DuckDuckGo >============================

def duckduckgo_search(query: str, max_results: int = 5) -> list[dict]:
    """
    DuckDuckGo text search — no API key needed.
    Requires: duckduckgo-search package  (uv add duckduckgo-search)
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError as exc:
        raise WebSearchError(
            "duckduckgo-search 패키지가 설치되지 않았습니다. `uv add duckduckgo-search`를 실행하세요."
        ) from exc

    results = []
    with DDGS() as ddgs:
        for hit in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": hit.get("title", ""),
                    "description": hit.get("body", ""),
                    "link": hit.get("href", ""),
                }
            )
    return results


# ===========================< Serper (Google) >============================

def serper_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Serper.dev Google Search API — real Google results.
    Requires: SERPER_API_KEY in environment.
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise WebSearchError("SERPER_API_KEY 환경 변수가 설정되지 않았습니다.")

    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": max_results, "gl": "kr", "hl": "ko"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "description": item.get("snippet", ""),
                "link": item.get("link", ""),
            }
        )
    return results


# ===========================< Shared formatter >============================

def format_results(results: list[dict]) -> str:
    if not results:
        return "검색 결과 없음"
    lines: list[str] = []
    for i, item in enumerate(results, start=1):
        title = _strip_html(item.get("title", ""))
        desc = _strip_html(item.get("description", ""))
        link = item.get("link", "")
        lines.append(f"{i}. {title}\n   {desc}\n   {link}")
    return "\n\n".join(lines)
