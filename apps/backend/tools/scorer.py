"""
카드별 점수 계산

역할:
- 검색 결과에서 동일한 card_name이 몇 번 등장하는지 카운트
- 등장 횟수 = score
"""

from collections import Counter
from typing import List, Dict, Any


class CardScorer:
    """카드 점수 계산기"""
    
    def calculate_scores(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        검색 결과에서 card_name 등장 횟수로 점수 계산
        
        Args:
            search_results: retriever에서 반환된 검색 결과 리스트
                각 항목은 {"id", "content", "metadata", "distance"} 형태
                metadata에 card_name이 포함되어 있음
        
        Returns:
            [{"card_name": str, "score": int}, ...]
            card_name과 등장 횟수(score)만 반환
        """
        if not search_results:
            return []
        
        # card_name 등장 횟수 카운트
        card_names = [
            result.get("metadata", {}).get("card_name", "Unknown")
            for result in search_results
        ]
        card_counts = Counter(card_names)
        
        # 결과 생성
        card_scores = [
            {"card_name": card_name, "score": count}
            for card_name, count in card_counts.items()
        ]
        
        return card_scores


# 테스트용 실행
if __name__ == "__main__":
    # 테스트 데이터
    mock_results = [
        {"id": "1", "content": "스타벅스 10% 할인", "metadata": {"card_name": "현대카드 X"}, "distance": 0.1},
        {"id": "2", "content": "전 가맹점 1% 할인", "metadata": {"card_name": "현대카드 X"}, "distance": 0.2},
        {"id": "3", "content": "커피 전문점 15% 할인", "metadata": {"card_name": "신한카드 Mr.Life"}, "distance": 0.15},
        {"id": "4", "content": "편의점 10% 할인", "metadata": {"card_name": "현대카드 X"}, "distance": 0.25},
        {"id": "5", "content": "대중교통 5% 할인", "metadata": {"card_name": "신한카드 Mr.Life"}, "distance": 0.3}
    ]
    
    scorer = CardScorer()
    scores = scorer.calculate_scores(mock_results)
    
    print("점수 계산 결과:")
    for card in scores:
        print(f"- {card['card_name']}: {card['score']}점")

