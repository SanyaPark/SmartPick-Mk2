from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid as uuid_lib

from apps.backend.core.database import get_supabase, fetch_markdown_from_s3
from apps.backend.models.schemas import RecommendationResponse, CardDetail, CategoryBenefit

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

# 프론트엔드 한글 카테고리 → DB card_benefits.category 매핑
CATEGORY_MAP = {
    "편의점/마트": "Shopping",
    "외식/배달": "Dining_FNB",
    "쇼핑": "Shopping",
    "교통": "Traffic",
    "이동통신": "Life",
    "월세": "Life",
    "보험": "Life",
    "주유/자량": "Traffic",
    "취미/여가": "Cultural",
    "병원/약국": "EduHealth",
}


class RecommendationRequest(BaseModel):
    user_id: str


@router.post("/", response_model=RecommendationResponse)
def get_recommendations(payload: RecommendationRequest):
    supabase = get_supabase()

    # 1. 유저의 소비 성향 조회
    prefs = supabase.table("user_spending_preferences").select("*").eq("user_id", payload.user_id).execute()
    if not prefs.data:
        raise HTTPException(status_code=400, detail="User preferences not found.")

    # 2. 가장 지출이 많은 카테고리 선정
    top_pref = sorted(prefs.data, key=lambda x: x["spending_amount"], reverse=True)[0]
    top_category_korean = top_pref["category_name"]
    top_category_db = CATEGORY_MAP.get(top_category_korean)

    if not top_category_db:
        raise HTTPException(status_code=400, detail=f"카테고리 매핑 실패: '{top_category_korean}'은 지원하지 않는 카테고리입니다.")

    # 3. card_benefits → card_benefit_groups → cards 관계 타고 카드 찾기
    try:
        # 3a. 해당 카테고리 혜택이 있는 benefit group_id 찾기
        benefit = supabase.table("card_benefits").select("group_id").eq("category", top_category_db).limit(1).execute()
        if not benefit.data:
            raise HTTPException(status_code=404, detail=f"해당 카테고리({top_category_db}) 혜택 데이터가 없습니다.")
        group_id = benefit.data[0]["group_id"]

        # 3b. group_id → card_id
        group = supabase.table("card_benefit_groups").select("card_id").eq("id", group_id).single().execute()
        card_id = group.data["card_id"]

        # 3c. card_id → 카드 상세 정보
        card_res = supabase.table("cards").select(
            "id, card_slug, card_name, card_company, annual_fee, min_performance, manual_file_path, image_url"
        ).eq("id", card_id).single().execute()
        card_data = card_res.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 오류: {e}")

    # 4. S3에서 해당 카드의 마크다운 원본 가져오기 (RAG Context)
    markdown_content = fetch_markdown_from_s3(card_data.get("manual_file_path"))

    # 5. 응답 스키마 구성
    recommended_card = CardDetail(
        card_id=uuid_lib.UUID(card_data["id"]),
        card_name=card_data["card_name"],
        card_company=card_data.get("card_company", ""),
        expected_monthly_benefit=30000,  # TODO: LLM 기반 계산 로직으로 교체
        expected_annual_benefit=360000,
        category_benefits=[
            CategoryBenefit(
                category_name=top_category_korean,
                benefit_description="최대 3만원 할인",  # TODO: card_benefits.content 조합
            )
        ],
        extra_benefits_summary=[],
        annual_fee_memo=f"연회비 {card_data.get('annual_fee', 0):,}원",
        min_performance_memo=f"전월실적 {card_data.get('min_performance', 0):,}원 이상",
        image_url=card_data.get("image_url"),
    )

    # 6. TODO: LLM 호출하여 markdown_content 기반 맞춤 큐레이션 생성
    # curation = llm.generate(context=markdown_content, user_profile=prefs.data)
    mock_curation = (
        f"매월 {top_category_korean} 관련 지출이 {top_pref['spending_amount']:,}원이신 고객님께 "
        f"{card_data['card_company']} {card_data['card_name']}를 추천드립니다."
    )

    return RecommendationResponse(
        user_id=payload.user_id,
        current_card=None,
        recommended_cards=[recommended_card],
        custom_curation=mock_curation,
        max_extra_benefit_amount=30000,
    )
