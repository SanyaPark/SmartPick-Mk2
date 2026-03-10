"""
최종 출력 형태로 정리

역할:
- retriever에서 가져온 전체 카드 정보를 최종 스키마로 변환
- 동일 카드의 여러 혜택을 detailed_benefits 리스트로 통합
"""

from pydantic import BaseModel
from typing import List, Dict, Any


# RAG 검색 결과 출력 스키마
class BenefitDetail(BaseModel):
    """개별 혜택 상세 정보"""
    category: str
    content: str
    conditions: str

class CardResult(BaseModel):
    """최종 카드 결과 스키마"""
    card_name: str
    card_company: str
    annual_fee: int
    min_performance: int
    major_categories: List[str]
    benefits_summary: str
    detailed_benefits: List[BenefitDetail]


class CardFormatter:
    """카드 정보 포맷터"""
    
    def format(self, card_data: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        카드 데이터를 최종 출력 형태로 변환
        
        Args:
            card_data: retriever.get_full_card_info()에서 반환된 데이터
                {card_name: [청크들]} 형태
        
        Returns:
            최종 스키마에 맞게 정리된 카드 정보 리스트
        """
        formatted_cards = []
        
        for card_name, chunks in card_data.items():
            if not chunks:
                continue
            
            # 첫 번째 청크에서 카드 메타데이터 추출 (모든 청크에서 동일)
            first_chunk = chunks[0]
            metadata = first_chunk.get("metadata", {})
            
            # major_categories 처리: 문자열이면 리스트로 변환
            major_categories = metadata.get("major_categories", [])
            if isinstance(major_categories, str):
                # "General, Travel, Life" 형태라면 파싱
                major_categories = [cat.strip() for cat in major_categories.split(",")]
            
            # detailed_benefits 리스트 구성
            detailed_benefits = []
            for chunk in chunks:
                chunk_meta = chunk.get("metadata", {})
                
                benefit = BenefitDetail(
                    category=chunk_meta.get("category", "기타"),
                    content=chunk_meta.get("content", chunk.get("content", "")),
                    conditions=chunk_meta.get("conditions", "")
                )
                detailed_benefits.append(benefit)
            
            # CardResult 생성
            card_result = CardResult(
                card_name=card_name,
                card_company=metadata.get("card_company", ""),
                annual_fee=metadata.get("annual_fee", 0),
                min_performance=metadata.get("min_performance", 0),
                major_categories=major_categories,
                benefits_summary=metadata.get("benefits_summary", ""),
                detailed_benefits=detailed_benefits
            )
            
            formatted_cards.append(card_result.model_dump())
        
        return formatted_cards


# 테스트용 실행
if __name__ == "__main__":
    # 테스트 데이터
    mock_card_data = {
        "현대카드 X": [
            {
                "id": "1",
                "content": "전월 실적 50만원 이상 시...",
                "metadata": {
                    "card_name": "현대카드 X",
                    "card_company": "현대카드",
                    "annual_fee": 50000,
                    "min_performance": 500000,
                    "major_categories": "General, Travel, Life",
                    "benefits_summary": "전 가맹점 1% 할인...",
                    "category": "전 가맹점 할인",
                    "content": "전월 실적 50만원 이상 시 국내외 모든 가맹점에서 결제 금액의 1%를 한도 제한 없이 청구 할인",
                    "conditions": "전월 이용 금액 50만원 이상 시 제공"
                }
            },
            {
                "id": "2",
                "content": "긴급할인 서비스...",
                "metadata": {
                    "card_name": "현대카드 X",
                    "card_company": "현대카드",
                    "annual_fee": 50000,
                    "min_performance": 500000,
                    "major_categories": "General, Travel, Life",
                    "benefits_summary": "전 가맹점 1% 할인...",
                    "category": "금융/여행 서비스",
                    "content": "긴급할인: 최대 50만 포인트를 미리 받아 결제 시 사용",
                    "conditions": "미상환액은 별도 청구됨"
                }
            }
        ]
    }
    
    formatter = CardFormatter()
    result = formatter.format(mock_card_data)
    
    import json
    print("포맷팅 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

