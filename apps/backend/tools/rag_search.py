"""
RAG 검색 메인 컨트롤러
전체 흐름: retriever → scorer → ranker → formatter
"""

from langchain_core.tools import tool

from apps.backend.tools.retriever import CardRetriever
from apps.backend.tools.scorer import CardScorer
from apps.backend.tools.ranker import CardRanker
from apps.backend.tools.formatter import CardFormatter


# tool 요청 스키마 산야님 개발 항목에 해당 내용 있으면 CardSearchInput 제거 후 class 연결
from pydantic import BaseModel, Field, field_validator
from typing import List

class CardSearchInput(BaseModel):
    """카드 추천 RAG 검색 Tool의 입력 스키마"""

    query: str = Field(
        description="사용자의 카드 검색 질의. "
                    "예: '커피 혜택이 좋은 카드', '주유 할인 많은 카드'"
    )

    budget_filter: int = Field(
        ge=0,
        description="사용자의 월 소비 금액 (원). "
                    "이 금액 이하의 전월실적(min_performance) 조건을 가진 카드만 필터링. "
                    "예: 300000"
    )

    keywords: List[str] = Field(
        description="사용자 소비패턴에서 추출한 카테고리 키워드"
                    "예: ['Shopping', 'Coffee', 'Traffic']"
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("검색어가 너무 짧습니다. 최소 2글자 이상 입력해주세요.")
        return v

    @field_validator('keywords')
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        if len(v) == 0:
            raise ValueError("keywords는 최소 1개 이상 필요합니다.")
        return [kw.strip().lower() for kw in v if kw.strip()]


# tool 함수 (워크플로우 7단계)
@tool("card_rag_search", args_schema=CardSearchInput)
def card_rag_search(query: str, budget_filter: int, keywords: list) -> list[dict]:
    """
    사용자 소비패턴과 예산에 맞는 카드를 RAG에서 검색 후 사용자 소비 패턴에 맞는 카드 목록을 반환하는 도구 함수

    흐름:
    1. retriever: budget과 keywords로 필터링 후 query로 유사도 검색
    2. scorer: 검색 결과에서 동일 card_name 등장 횟수로 점수 계산
    3. ranker: 점수 기준 내림차순 정렬
    4. retriever: 상위 카드들의 전체 혜택 재검색
    5. formatter: 최종 출력 형태로 정리
    
    Args:
        query: 사용자의 카드 혜택 관련 질문
        keywords: 사용자 소비패턴에서 추출한 카테고리 키워드
        budget: 사용자의 월 예상 사용 금액 (전월 실적 필터링용)
    
    Returns:
        List[dict]: 추천 카드 정보 리스트
    """

    # Step 1: 컴포넌트 초기화
    retriever = CardRetriever()
    scorer = CardScorer()
    ranker = CardRanker()
    formatter = CardFormatter()
    
    # Step 2: 필터링 + 유사도 검색
    # budget으로 min_performance 필터링, keywords로 major_categories 필터링
    # query로 content 유사도 검색
    search_results = retriever.search(
        query=query,
        budget_filter=budget_filter,
        category_filter=keywords,
    )
    
    if not search_results:
        return []
    
    # Step 3: 점수 계산 (동일 card_name 등장 횟수)
    card_scores = scorer.calculate_scores(search_results)
    
    # Step 4: 점수 기준 정렬
    ranked_cards = ranker.rank(card_scores)
    
    # Step 5: 상위 카드들의 전체 혜택 검색
    top_card_names = [card["card_name"] for card in ranked_cards]
    full_card_data = retriever.get_full_card_info(top_card_names)
    
    # Step 6: 최종 출력 형태로 정리
    formatted_results = formatter.format(full_card_data)
    
    return formatted_results


# 테스트용 실행
if __name__ == "__main__":
    # 테스트 실행
    result = card_rag_search.invoke({
        "query": "커피 많이 마시는데 혜택 좋은 카드 추천해줘",
        "keywords": ["Coffee", "Shopping"],
        "budget": 500000
    })
    
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))

