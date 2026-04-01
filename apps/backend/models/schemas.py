from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

# --- Request Models (Frontend -> Backend) ---

class CategorySpending(BaseModel):
    category_name: str = Field(..., description="Name of the chosen category (e.g., '편의점/마트')")
    spending_amount: int = Field(..., description="Average monthly spending mapped to this category")

class UserPreferencesUpdate(BaseModel):
    # Until Auth is fully integrated (JWT), we explicitly take the UUID here for testing
    user_id: UUID = Field(..., description="UUID in auth.users and public.user_profiles")
    nickname: Optional[str] = Field("테스터", description="Nickname to create profile if not exists")
    total_monthly_spending: int = Field(0, description="Overall total monthly spending (from top slider)")
    categories: List[CategorySpending] = Field(default_factory=list, description="Detailed category spendings (2~5 items)")
    owned_cards: List[UUID] = Field(default_factory=list, description="UUIDs of cards the user already owns")


# --- Response Models (Backend -> Frontend) ---

class CategoryBenefit(BaseModel):
    category_name: str = Field(..., description="예: '외식/배달', '교통'")
    benefit_description: str = Field(..., description="예: '최대 4만원 할인' 또는 '해당사항 없음'")

class CardDetail(BaseModel):
    card_id: UUID
    card_name: str
    card_company: str
    
    expected_monthly_benefit: int = Field(..., description="예상 최대 월별 혜택금액 (숫자)")
    expected_annual_benefit: int = Field(..., description="1년간 예상 혜택금액 (숫자)")
    
    category_benefits: List[CategoryBenefit] = Field(default_factory=list, description="주요 소비 카테고리별 혜택 리스트")
    
    extra_benefits_summary: List[str] = Field(default_factory=list, description="하단 회색 기타 혜택 요약 (예: ['커피 30% 할인', '연회비 10,000원'])")
    annual_fee_memo: str = Field("", description="연회비 정보 텍스트")
    min_performance_memo: str = Field("", description="전월실적 조건 텍스트")
    
    image_url: Optional[str] = None

class RecommendationResponse(BaseModel):
    user_id: str
    
    # 비교를 위한 기존(사용 중인) 카드 정보 (없을 수도 있음)
    current_card: Optional[CardDetail] = Field(None, description="유저가 선택한 기존 카드")
    
    # 추천 알고리즘/LLM이 뽑아준 새로운 카드 목록
    recommended_cards: List[CardDetail] = Field(..., description="새로 추천하는 카드 리스트")
    
    # 하단 LLM 맞춤 큐레이션 (종합 추천 이유)
    custom_curation: str = Field(..., description="OO님을 위한 맞춤 큐레이션 (LLM 생성 텍스트)")
    
    # 추천 바꿀 시 얻게 되는 추가 혜택 총액 (UI 우측 상단 표시용)
    max_extra_benefit_amount: int = Field(0, description="새로운 카드로 바꾸시면 지금보다 최대 N만원 이득")

