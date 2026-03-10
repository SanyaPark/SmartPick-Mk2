
"""
카드 순위 결정

역할:
- scorer에서 계산된 점수를 기준으로 내림차순 정렬
"""


from typing import List, Dict, Any


class CardRanker:
    """카드 순위 결정기"""
    
    def rank(
        self,
        card_scores: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        점수 기준 내림차순 정렬
        
        Args:
            card_scores: scorer에서 반환된 카드별 점수 리스트
                [{"card_name": str, "score": int}, ...]
        
        Returns:
            점수 내림차순으로 정렬된 카드 리스트
        """
        if not card_scores:
            return []
        
        # 점수 기준 내림차순 정렬
        # 점수가 같으면 card_name 알파벳순 (일관성 유지)
        sorted_cards = sorted(
            card_scores,
            key=lambda x: (-x["score"], x["card_name"])
        )
        
        # 상위 N개만 반환
        return sorted_cards


# 테스트용 실행
if __name__ == "__main__":
    # 테스트 데이터
    mock_scores = [
        {"card_name": "신한카드 Mr.Life", "score": 2},
        {"card_name": "현대카드 X", "score": 3},
        {"card_name": "삼성카드 taptap O", "score": 1},
        {"card_name": "KB국민 My WE:SH", "score": 2}
    ]
    
    ranker = CardRanker()
    ranked = ranker.rank(mock_scores)
    
    print("정렬 결과:")
    for i, card in enumerate(ranked, 1):
        print(f"{i}. {card['card_name']}: {card['score']}점")

