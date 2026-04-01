import os
from dotenv import load_dotenv
from supabase import create_client, Client

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def test_recommendation_with_groups(target_spend=600000, preferred_categories=["Cultural", "Travel"]):
    print(f"\n🔍 [가상 유저 시나리오 테스트]")
    print(f"목표 실적: 월 {target_spend}원 이하 | 선호 카테고리: {preferred_categories}")
    print("=" * 60)
    
    # Supabase의 강력한 내포 쿼리(Nested Select)를 이용해 3단 구조 데이터를 한 방에 가져옵니다.
    res = supabase.table("cards") \
        .select("""
            id,
            card_name,
            card_company,
            annual_fee,
            card_benefit_groups (
                group_name,
                group_type,
                card_benefits (
                    category,
                    content
                )
            )
        """) \
        .lte("min_performance", target_spend) \
        .execute()
        
    eligible_cards = res.data
    card_scores = []
    
    for c in eligible_cards:
        score = 0
        matched_details = []
        
        # 그룹들을 순회
        groups = c.get("card_benefit_groups", [])
        for g in groups:
            group_name = g.get("group_name")
            benefits = g.get("card_benefits", [])
            for b in benefits:
                b_cat = b.get("category", "") or ""
                # 선호 카테고리와 단어가 조금이라도 겹치면 점수 부여
                if any(pref.lower() in b_cat.lower() for pref in preferred_categories):
                    score += 1
                    # 출력할 때 '어떤 그룹(기본/선택) 소속 혜택'인지 표기
                    matched_details.append(f"[{group_name}] ({b_cat}) {b.get('content', '')}")
                    
        card_scores.append({
            "card_name": c["card_name"],
            "company": c["card_company"],
            "fee": c["annual_fee"],
            "score": score,
            "matches": matched_details
        })
        
    # 점수 내림차순, 동일 점수 시 연회비 오름차순
    card_scores.sort(key=lambda x: (-x["score"], x["fee"]))
    
    print("\n🏆 추천 카드 TOP 3 (혜택 그룹 소속 표기):")
    for idx, c in enumerate(card_scores[:3]):
        print(f"\n#{idx + 1} {c['card_name']} ({c['company']})")
        print(f"   ➤ 매칭 점수: {c['score']}점 | 연회비: {c['fee']}원")
        print("   ➤ 매칭된 강력한 혜택 목록:")
        for m in c["matches"]:
            print(f"      ✔ {m}")

if __name__ == "__main__":
    test_recommendation_with_groups(target_spend=600000, preferred_categories=["Cultural", "Travel"])
