"""
LLM으로 이미 청킹된 JSON 파일을 임베딩하여 ChromaDB에 저장하는 스크립트

사용법:
    uv run python -m apps.backend.chunker.embed_chunked_json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from apps.backend.chunker.chunk_models import Chunk, EmbeddingRecord
from apps.backend.chunker.embedding_client import UpstageEmbeddingClient
from apps.backend.chunker.vector_store import ChromaVectorStore


# .env 파일 로드
load_dotenv()


def slugify(value: str) -> str:
    """카드 이름을 chunk_id용 slug로 변환"""
    value = re.sub(r"[^0-9a-zA-Z가-힣]+", "-", value).strip("-")
    return value or "chunk"


def load_chunked_json(file_path: Path) -> Dict[str, Any]:
    """청킹된 JSON 파일 로드"""
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def convert_to_chunks(data: Dict[str, Any]) -> List[Chunk]:
    """
    LLM 청킹 결과를 Chunk 객체 리스트로 변환
    
    입력 JSON 형식:
    {
        "chunk1": {
            "card_name": "...",
            "card_company": "...",
            "annual_fee": 20000,
            "min_performance": 500000,
            "major_categories": "Cultural, Shopping",
            "benefits_summary": "...",
            "category": "...",
            "content": "...",
            "conditions": "..."
        },
        "chunk2": { ... }
    }
    """
    chunks = []
    
    for chunk_key, chunk_data in data.items():
        card_name = chunk_data.get("card_name", "Unknown")
        base_slug = slugify(card_name)
        
        # chunk_id 생성: {card_slug}-benefit-{번호}
        chunk_num = chunk_key.replace("chunk", "")
        try:
            chunk_num = int(chunk_num)
        except ValueError:
            chunk_num = len(chunks) + 1
        
        chunk = Chunk(
            chunk_id=f"{base_slug}-benefit-{chunk_num:02d}",
            card_name=card_name,
            card_company=chunk_data.get("card_company", "Unknown"),
            chunk_type="benefit",
            content=chunk_data.get("content", ""),
            category=chunk_data.get("category"),
            annual_fee=chunk_data.get("annual_fee"),
            min_performance=chunk_data.get("min_performance"),
            major_categories=chunk_data.get("major_categories"),
            benefits_summary=chunk_data.get("benefits_summary"),
            conditions=chunk_data.get("conditions"),
        )
        chunks.append(chunk)
    
    return chunks


def embed_and_store(
    chunks: List[Chunk],
    embedding_client: UpstageEmbeddingClient,
    vector_store: ChromaVectorStore
) -> int:
    """청크를 임베딩하고 벡터 스토어에 저장"""
    
    # 유효한 content가 있는 청크만 필터링
    valid_chunks = [c for c in chunks if c.content and c.content.strip()]
    
    if not valid_chunks:
        print("임베딩할 유효한 청크가 없습니다.")
        return 0
    
    # 임베딩 생성
    texts = [chunk.content for chunk in valid_chunks]
    vectors = embedding_client.embed_texts(texts)
    
    # EmbeddingRecord 생성
    records = [
        EmbeddingRecord(chunk=chunk, vector=vector)
        for chunk, vector in zip(valid_chunks, vectors)
    ]
    
    # 벡터 스토어에 저장
    vector_store.upsert(records)
    
    return len(records)


def process_single_file(
    file_path: Path,
    embedding_client: UpstageEmbeddingClient,
    vector_store: ChromaVectorStore
) -> int:
    """단일 JSON 파일 처리"""
    # print(f"처리 중: {file_path}")
    
    data = load_chunked_json(file_path)
    chunks = convert_to_chunks(data)
    
    if not chunks:
        # print(f"  → 청크 없음, 건너뜀")
        return 0
    
    count = embed_and_store(chunks, embedding_client, vector_store)
    # print(f"  → {count}개 청크 임베딩 완료")
    
    return count


def main():
    parser = argparse.ArgumentParser(
        description="LLM 청킹된 JSON을 임베딩하여 ChromaDB에 저장"
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="단일 JSON 파일 경로"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("datasets/json/"),  # 기본 경로 설정
        help="JSON 파일들이 있는 디렉토리 경로"
    )
    parser.add_argument(
        "--chroma-dir",
        type=Path,
        default=Path("datasets/embeddings_cache/chroma_db"),
        help="ChromaDB 저장 경로 (기본: datasets/embeddings_cache/chroma_db)"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="card_disclosures",
        help="ChromaDB 컬렉션 이름 (기본: card_disclosures)"
    )
    
    args = parser.parse_args()
    
    if not args.input and not args.input_dir:
        parser.error("--input 또는 --input-dir 중 하나는 필수입니다")
    
    # API 키 확인
    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        raise ValueError("UPSTAGE_API_KEY 환경 변수가 설정되지 않았습니다")
    
    # 클라이언트 초기화
    embedding_client = UpstageEmbeddingClient(api_key=api_key)
    vector_store = ChromaVectorStore(
        persist_directory=args.chroma_dir,
        collection_name=args.collection
    )
    
    total_count = 0
    
    if args.input:
        # 단일 파일 처리
        total_count = process_single_file(args.input, embedding_client, vector_store)
    
    elif args.input_dir:
        # 디렉토리 내 모든 JSON 파일 처리
        json_files = sorted(args.input_dir.glob("**/*.json"))
        if not json_files:
            print(f"JSON 파일을 찾을 수 없습니다: {args.input_dir}")
            return
        
        for json_file in json_files:
            count = process_single_file(json_file, embedding_client, vector_store)
            total_count += count
    
    # print(f"\n총 {total_count}개 청크 임베딩 완료")
    # print(f"저장 위치: {args.chroma_dir}")


if __name__ == "__main__":
    main()
