from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
ENV_PATH = BACKEND_ROOT / ".env"


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        os.environ.setdefault(key, value)


_load_env_file()


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    backend_root: Path
    datasets_dir: Path
    pdf_dir: Path
    text_dir: Path
    chunks_dir: Path
    index_csv: Path
    chroma_dir: Path
    chunk_token_size: int
    chunk_overlap: int
    enable_benefit_regex: bool
    vector_db: Literal["chroma"]
    upstage_api_key: str
    upstage_model: str


@lru_cache()
def get_settings() -> Settings:
    # Everything in root datasets
    datasets_dir = REPO_ROOT / "datasets"
    pdf_dir = datasets_dir / "pdfs"
    text_dir = datasets_dir / "text"
    index_csv = datasets_dir / "index.csv"
    chunks_dir = datasets_dir / "chunks"
    chroma_dir = datasets_dir / "embeddings_cache" / "chroma_db"

    # Ensure processed directories exist
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    upstage_api_key = os.environ.get("UPSTAGE_API_KEY", "")
    if not upstage_api_key:
        raise RuntimeError(
            "UPSTAGE_API_KEY is required. Please add it to apps/backend/.env"
        )

    return Settings(
        repo_root=REPO_ROOT,
        backend_root=BACKEND_ROOT,
        datasets_dir=datasets_dir,
        pdf_dir=pdf_dir,
        text_dir=text_dir,
        chunks_dir=chunks_dir,
        index_csv=index_csv,
        chroma_dir=chroma_dir,
        chunk_token_size=int(os.environ.get("CHUNK_TOKEN_SIZE", 500)),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", 60)),
        enable_benefit_regex=os.environ.get("ENABLE_BENEFIT_REGEX", "true").lower()
        in ("1", "true", "yes"),
        vector_db="chroma",
        upstage_api_key=upstage_api_key,
        upstage_model=os.environ.get(
            "UPSTAGE_EMBEDDING_MODEL", "embedding-query"
        ),
    )
