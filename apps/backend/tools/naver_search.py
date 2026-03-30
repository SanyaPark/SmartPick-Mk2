import json
import os
import urllib.parse
import urllib.request
from typing import List, Dict, Optional


NAVER_SEARCH_ENDPOINT = "https://openapi.naver.com/v1/search/blog.json"


class NaverSearchError(Exception):
    pass


def _get_headers() -> Dict[str, str]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise NaverSearchError(
            "NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 환경 변수가 설정되지 않았습니다."
        )
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def search_blog(
    query: str,
    display: int = 5,
    start: int = 1,
    sort: str = "sim",
) -> List[Dict[str, Optional[str]]]:
    """
    네이버 블로그 검색 API를 호출해 결과를 반환합니다.
    반환 형식: [{"title": ..., "description": ..., "link": ..., "bloggername": ..., "postdate": ...}, ...]
    """
    if not query:
        return []

    params = {
        "query": query,
        "display": max(1, min(display, 10)),
        "start": max(1, min(start, 1000)),
        "sort": sort,
    }
    url = NAVER_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)
    headers = _get_headers()

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        raise NaverSearchError(f"네이버 검색 API 호출 실패: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NaverSearchError("네이버 검색 API 응답 파싱 실패") from exc

    items = data.get("items", [])
    results = []
    for it in items:
        results.append(
            {
                "title": it.get("title"),
                "description": it.get("description"),
                "link": it.get("link"),
                "bloggername": it.get("bloggername"),
                "postdate": it.get("postdate"),
            }
        )
    return results
