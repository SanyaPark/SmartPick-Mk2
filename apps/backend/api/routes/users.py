from fastapi import APIRouter, HTTPException
from apps.backend.models.schemas import UserPreferencesUpdate
from apps.backend.core.database import get_supabase

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/me/preferences")
def update_user_preferences(payload: UserPreferencesUpdate):
    """
    Save the user survey (total spending, categories, owned cards).
    Replaces any existing preferences and owned cards for this user.
    """
    supabase = get_supabase()
    user_id = str(payload.user_id)
    
    # 1. Update total tracking in user_profiles
    try:
        # Upsert the profile. Note: If auth.users FK constraint is strictly enabled,
        # user_id MUST exist in auth.users manually created via Supabase dashboard first!
        supabase.table("user_profiles").upsert({
            "id": user_id, 
            "nickname": payload.nickname,
            "total_monthly_spending": payload.total_monthly_spending
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update user_profiles. (Check if UUID {user_id} exists in auth.users). Error: {e}")

    # 2. Reset and Insert Tracking Categories
    try:
        supabase.table("user_spending_preferences").delete().eq("user_id", user_id).execute()
        
        if payload.categories:
            pref_inserts = [
                {"user_id": user_id, "category_name": p.category_name, "spending_amount": p.spending_amount}
                for p in payload.categories
            ]
            supabase.table("user_spending_preferences").insert(pref_inserts).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update categories: {e}")

    # 3. Reset and Insert Owned Cards
    try:
        supabase.table("user_owned_cards").delete().eq("user_id", user_id).execute()
        
        if payload.owned_cards:
            card_inserts = [{"user_id": user_id, "card_id": str(cid)} for cid in payload.owned_cards]
            supabase.table("user_owned_cards").insert(card_inserts).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update owned cards: {e}")

    return {"status": "success", "message": "User preferences updated successfully."}
