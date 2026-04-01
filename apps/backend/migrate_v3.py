import os
import json
import glob
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from apps/backend/.env
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

supabase: Client = create_client(url, key)

json_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../datasets/json_v3"))
json_files = glob.glob(f"{json_dir}/**/*.json", recursive=True)

print(f"Found {len(json_files)} json_v3 files.")

for file in json_files:
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Insert into cards table
    card_meta = data.get("card_meta", {})
    card_slug = card_meta.get("card_id", "unknown_slug")
    card_name = card_meta.get("card_name", "Unknown")
    
    # Check if card already exists to avoid unique constraint violation
    existing_card = supabase.table("cards").select("id").eq("card_slug", card_slug).execute()
    
    if len(existing_card.data) > 0:
        print(f"Card {card_name} already exists. Skipping insertion for cards table.")
        continue
    else:
        card_insert_payload = {
            "card_slug": card_slug,
            "card_name": card_name,
            "card_company": card_meta.get("card_company", ""),
            "annual_fee": card_meta.get("annual_fee", 0),
            "min_performance": card_meta.get("minimum_performance", 0),
            "reward_currency": card_meta.get("reward_currency", "KRW"),
            "currency_rate": card_meta.get("currency_to_krw_rate", 1.0),
            "image_url": None
        }
        res = supabase.table("cards").insert(card_insert_payload).execute()
        card_id = res.data[0]['id']
        
    print(f"Inserted card: {card_name} UUID: {card_id}")
    
    # 2. Insert into benefit groups table
    benefit_groups = data.get("benefit_groups", [])
    
    # We maintain a mapping from JSON group_id -> DB UUID
    group_uuid_map = {}
    
    # *Important*: New schema connects card_benefits -> card_benefit_groups.
    # What if a benefit has NO group (group_id = null)? 
    # We must create a default standalone group per card to hold these benefits.
    default_group_slug = f"G_DEFAULT_{card_slug.upper()}"
    default_group_payload = {
        "card_id": card_id,
        "group_slug": default_group_slug,
        "group_name": "기본 제공 혜택",
        "group_type": "INDEPENDENT",
        "limit_amount": 0
    }
    res_def_group = supabase.table("card_benefit_groups").insert(default_group_payload).execute()
    group_uuid_map[None] = res_def_group.data[0]['id']
    group_uuid_map[""] = res_def_group.data[0]['id']
    
    # Insert actual groups from JSON
    for group in benefit_groups:
        g_slug = group.get("group_id")
        g_payload = {
            "card_id": card_id,
            "group_slug": g_slug,
            "group_name": group.get("group_name", ""),
            "group_type": group.get("group_type", ""),
            "limit_amount": group.get("limit_amount", 0)
        }
        res_g = supabase.table("card_benefit_groups").insert(g_payload).execute()
        group_uuid_map[g_slug] = res_g.data[0]['id']
    
    print(f"  -> Inserted {len(benefit_groups) + 1} benefit groups.")

    # 3. Insert benefits into detailed table
    benefits = data.get("benefits", [])
    benefit_payloads = []
    
    for benefit in benefits:
        b_group_slug = benefit.get("group_id")
        # Map to the UUID (fallback to default group if null)
        db_group_uuid = group_uuid_map.get(b_group_slug, group_uuid_map[None])
        
        benefit_payloads.append({
            "group_id": db_group_uuid,
            "benefit_slug": benefit.get("benefit_id"),
            "category": benefit.get("category", ""),
            "content": benefit.get("content", ""),
            "reward_type": benefit.get("reward_type", ""),
            "calculation_rule": benefit.get("calculation_rule", {}),
            "transaction_conditions": benefit.get("transaction_conditions", {}),
            "ui_warnings": benefit.get("ui_warnings", []) # Supabase SDK handles list -> text[] natively
        })
    
    if benefit_payloads:
        supabase.table("card_benefits").insert(benefit_payloads).execute()
        print(f"  -> Inserted {len(benefit_payloads)} benefits for {card_name}")

print("Migration completed successfully!")
