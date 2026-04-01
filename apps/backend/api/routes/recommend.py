from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid

from apps.backend.core.database import get_supabase, fetch_markdown_from_s3
from apps.backend.models.schemas import RecommendationResponse, CardDetail, CategoryBenefit

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

class RecommendationRequest(BaseModel):
    user_id: str

@router.post("/", response_model=RecommendationResponse)
def get_recommendations(payload: RecommendationRequest):
    supabase = get_supabase()
    
    # 1. Fetch user spending preferences
    prefs = supabase.table("user_spending_preferences").select("*").eq("user_id", payload.user_id).execute()
    if not prefs.data:
        raise HTTPException(status_code=400, detail="User preferences not found.")
    
    top_category = sorted(prefs.data, key=lambda x: x["spending_amount"], reverse=True)[0]
    
    # 2. Fetch cards matching the category
    matching_benefits = supabase.table("card_benefits").select("card_id").eq("category_name", top_category["category_name"]).limit(1).execute()
    if not matching_benefits.data:
        raise HTTPException(status_code=404, detail="No matching cards found for this category.")
        
    card_id = matching_benefits.data[0]["card_id"]
    
    # 3. Fetch card Markdown paths
    card = supabase.table("cards").select("id, card_name, card_company, manual_file_path").eq("id", card_id).single().execute()
    card_data = card.data
    
    # 4. Mock the response conforming to the new schema
    recommended_card = CardDetail(
        card_id=uuid.UUID(card_data["id"]),
        card_name=card_data["card_name"],
        card_company=card_data.get("card_company", "기타"),
        expected_monthly_benefit=30000,
        expected_annual_benefit=360000,
        category_benefits=[
            CategoryBenefit(category_name=top_category["category_name"], benefit_description="최대 3만원 할인"),
            CategoryBenefit(category_name="외식/배달", benefit_description="최대 4만원 할인")
        ],
        extra_benefits_summary=["커피전문점 30% 할인", "마켓컬리 20% 할인"],
        annual_fee_memo="국내전용 10,000원 / 해외겸용 10,000원",
        min_performance_memo="전월실적 30만원 이상",
        image_url=None
    )
    
    # 5. TODO: RAG LLM Call for Curation
    mock_reasoning = f"매월 평균 소비 금액이 60만원이고 월세와 배달음식 지출이 크신 은정님께 가장 특화된 카드입니다."
    
    return RecommendationResponse(
        user_id=payload.user_id,
        current_card=None, # 생략 가능
        recommended_cards=[recommended_card],
        custom_curation=mock_reasoning,
        max_extra_benefit_amount=20000
    )
