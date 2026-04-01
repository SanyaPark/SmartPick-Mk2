import os
from dotenv import load_dotenv
from supabase import create_client, Client

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=env_path)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

# Global singleton client
supabase: Client = create_client(url, key)

def get_supabase() -> Client:
    return supabase

def fetch_markdown_from_s3(file_path: str, bucket_name: str = "card-docs") -> str:
    """Helper to download text/markdown files from Supabase Storage"""
    if not file_path:
        return ""
    try:
        res = supabase.storage.from_(bucket_name).download(file_path)
        return res.decode("utf-8")
    except Exception as e:
        print(f"Error downloading {file_path} from {bucket_name}: {e}")
        return ""
