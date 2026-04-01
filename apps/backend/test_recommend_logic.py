"""
추천 파이프라인 통합 테스트
- Supabase auth 없이, 기존 user_profiles 유저 UUID를 재활용하거나
  user_spending_preferences에 직접 mock 데이터를 insert해 테스트합니다.
"""
import os, sys, json, uuid
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# ── 1. 기존 유저 프로파일에서 UUID 1개 가져오기 ──────────────────────────────
print("=== 1. 기존 user_profiles에서 테스트 유저 UUID 탐색 ===")
profiles = sb.table("user_profiles").select("id").limit(1).execute()

if profiles.data:
    test_user_id = profiles.data[0]["id"]
    print(f"✅ 기존 유저 재활용: {test_user_id}")
else:
    print("❌ user_profiles에 유저가 없습니다. Supabase Auth 대시보드에서 유저를 먼저 생성해주세요.")
    sys.exit(1)

# ── 2. 해당 유저의 소비 성향을 mock 데이터로 초기화 ──────────────────────────
print("\n=== 2. 소비 성향 mock 데이터 Insert ===")
sb.table("user_spending_preferences").delete().eq("user_id", test_user_id).execute()

mock_prefs = [
    {"user_id": test_user_id, "category_name": "교통", "spending_amount": 120000},
    {"user_id": test_user_id, "category_name": "외식/배달", "spending_amount": 280000},
    {"user_id": test_user_id, "category_name": "쇼핑", "spending_amount": 80000},
]
res = sb.table("user_spending_preferences").insert(mock_prefs).execute()
print(f"✅ {len(res.data)}개 카테고리 선호도 저장 완료")

# ── 3. FastAPI TestClient로 /recommendations/ 엔드포인트 호출 ─────────────────
print("\n=== 3. POST /recommendations/ 엔드포인트 테스트 ===")
from fastapi.testclient import TestClient
from apps.backend.main import app
client = TestClient(app)

res_rec = client.post("/recommendations/", json={"user_id": test_user_id})
print(f"Status: {res_rec.status_code}")

if res_rec.status_code != 200:
    print(f"❌ 실패: {res_rec.text}")
    sys.exit(1)

data = res_rec.json()

# ── 4. 결과 출력 ──────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("🎯 SmartPick 카드 추천 결과")
print("="*60)

if data.get("recommended_cards"):
    card = data["recommended_cards"][0]
    print(f"💳 추천 카드: {card['card_company']} {card['card_name']}")
    print(f"💰 예상 월 혜택: 최대 {card['expected_monthly_benefit']:,}원")
    print(f"📅 연간 환산: {card['expected_annual_benefit']:,}원")
    print(f"\n📊 카테고리별 혜택:")
    for cb in card.get("category_benefits", []):
        print(f"   [{cb['category_name']}] {cb['benefit_description']}")
    print(f"\n🏷️  {card['annual_fee_memo']}")
    print(f"🏷️  {card['min_performance_memo']}")

print(f"\n💡 맞춤 큐레이션:")
print(f'   "{data["custom_curation"]}"')
print(f"\n🎁 기존 대비 추가 혜택: 최대 {data['max_extra_benefit_amount']:,}원")
print("="*60)
print("\n✅ 카드 추천 파이프라인 정상 작동 확인!")
