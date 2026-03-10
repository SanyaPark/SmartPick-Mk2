from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Chunk:
    chunk_id: str
    card_name: str
    card_company: str
    chunk_type: str
    content: str
    category: Optional[str] = None
    # RAG 검색용 필드 추가
    annual_fee: Optional[int] = None
    min_performance: Optional[int] = None
    major_categories: Optional[str] = None  # "General, Shopping, Coffee" 형태
    benefits_summary: Optional[str] = None
    conditions: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkBatch:
    chunks: List[Chunk]


@dataclass
class EmbeddingRecord:
    chunk: Chunk
    vector: List[float]
