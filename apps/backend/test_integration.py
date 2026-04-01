import os, sys, json
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. Load env and setup Supabase
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Error: Missing SUPABASE_URL or SUPABASE_KEY")
    sys.exit(1)

supabase: Client = create_client(url, key)

# 2. Setup FastAPI TestClient
try:
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    client = TestClient(app)
except Exception as e:
    print(f"Error loading FastAPI app: {e}")
    sys.exit(1)

# 3. Create a Dummy User via Auth SignUp to bypass ForeignKey constraints
print("=== 1. Creating Dummy User in auth.users ===")
dummy_email = "tester_demo@smartpick.com"
dummy_password = "securePassword123!"
auth_res = None
try:
    auth_res = supabase.auth.sign_up({
        "email": dummy_email,
        "password": dummy_password
    })
    user_id = auth_res.user.id
    print(f"✅ Success! Created User ID: {user_id}")
except Exception as e:
    # If the user already exists, try to log in to get the UUID
    try:
        auth_res = supabase.auth.sign_in_with_password({"email": dummy_email, "password": dummy_password})
        user_id = auth_res.user.id
        print(f"✅ Success! Logged in existing User ID: {user_id}")
    except Exception as login_err:
        print(f"Failed to create or login dummy user: {login_err}")
        sys.exit(1)

# 4. Test User Preferences Saving (Onboarding API)
print("\n=== 2. Testing POST /users/me/preferences ===")
payload = {
    "user_id": user_id,
    "nickname": "Integration Tester",
    "total_monthly_spending": 600000,
    "categories": [
        {"category_name": "교통", "spending_amount": 100000},
        {"category_name": "외식/배달", "spending_amount": 250000}
    ],
    "owned_cards": []
}
res_prefs = client.post("/users/me/preferences", json=payload)
if res_prefs.status_code == 200:
    print("✅ Success! Preferences Saved.")
else:
    print(f"❌ Failed: {res_prefs.status_code} - {res_prefs.text}")
    sys.exit(1)

# 5. Test Card Recommendation Pipeline (RAG API)
print("\n=== 3. Testing POST /recommendations/ ===")
res_rec = client.post("/recommendations/", json={"user_id": user_id})
if res_rec.status_code == 200:
    print("✅ Success! Recommendation Generated.")
    recommendation_data = res_rec.json()
    
    # Beautiful Output
    print("\n" + "="*50)
    print("🎯 스마트픽 카드 추천 결과 🎯")
    print("="*50)
    
    # We parse the mock schema response!
    user = recommendation_data.get("user_id")
    recommended = recommendation_data.get("recommended_cards", [])[0]
    
    print(f"💳 추천 카드명: {recommended.get('card_company')} {recommended.get('card_name')}")
    print(f"💰 예상 월 혜택: 최대 {recommended.get('expected_monthly_benefit'):,}원")
    print("\n📊 세부 혜택:")
    for cat in recommended.get('category_benefits', []):
        print(f"  - [{cat.get('category_name')}] {cat.get('benefit_description')}")
    
    print(f"\n💡 은정님(테스터)을 위한 AI 맟춤 큐레이션:")
    print(f"  \"{recommendation_data.get('custom_curation')}\"")
    print("="*50 + "\n")
    
else:
    print(f"❌ Failed: {res_rec.status_code} - {res_rec.text}")
