from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import chromadb

from .chunk_models import Chunk, EmbeddingRecord


class VectorStore:
    def upsert(
        self, records: Iterable[EmbeddingRecord]
    ) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    def __init__(
        self, persist_directory: Path, collection_name: str = "card_disclosures"
    ) -> None:
        persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert(self, records: Iterable[EmbeddingRecord]) -> None:
        documents: List[str] = []
        metadatas: List[dict] = []
        ids: List[str] = []
        embeddings: List[List[float]] = []

        for record in records:
            chunk = record.chunk
            ids.append(chunk.chunk_id)
            documents.append(chunk.content)
            embeddings.append(record.vector)
            
            # 메타데이터 구성 - RAG 검색에 필요한 모든 필드 포함
            metadata = {
                "chunk_type": chunk.chunk_type,
                "card_name": chunk.card_name,
                "card_company": chunk.card_company,
            }
            
            # Optional 필드들 - None이 아닌 경우만 추가
            if chunk.category:
                metadata["category"] = chunk.category
            if chunk.annual_fee is not None:
                metadata["annual_fee"] = chunk.annual_fee
            if chunk.min_performance is not None:
                metadata["min_performance"] = chunk.min_performance
            if chunk.major_categories:
                metadata["major_categories"] = chunk.major_categories
            if chunk.benefits_summary:
                metadata["benefits_summary"] = chunk.benefits_summary
            if chunk.conditions:
                metadata["conditions"] = chunk.conditions

            # 추가 메타데이터 (있는 경우)
            metadata.update(
                {k: str(v) for k, v in chunk.metadata.items() if v is not None}
            )
            metadatas.append(metadata)

        if not documents:
            return

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
