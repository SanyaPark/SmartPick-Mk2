from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .chunk_extractor import generate_chunks, slugify
from .chunk_models import Chunk, EmbeddingRecord
from .config import get_settings
from .embedding_client import UpstageEmbeddingClient
from .vector_store import ChromaVectorStore


def load_index(index_path: Path) -> Dict[str, Dict[str, str]]:
    if not index_path.exists():
        return {}
    mapping: Dict[str, Dict[str, str]] = {}
    with index_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            card_name = row.get("card_name")
            if card_name:
                mapping[card_name] = row
    return mapping


def dump_chunks(chunks: List[Chunk], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")


def run_pipeline(
    card_filter: Optional[Iterable[str]] = None,
    chunks_only: bool = False,
    embed_only: bool = False,
) -> None:
    settings = get_settings()
    index_map = load_index(settings.index_csv)
    card_filter_set = {name.strip() for name in card_filter} if card_filter else None

    text_files = sorted(settings.text_dir.rglob("*.json"))
    if not text_files:
        print("No extracted text files found in datasets/text")
        return

    embedding_client = (
        None
        if chunks_only
        else UpstageEmbeddingClient(
            api_key=settings.upstage_api_key,
            model=settings.upstage_model,
        )
    )
    vector_store = None if chunks_only else ChromaVectorStore(settings.chroma_dir)

    for text_file in text_files:
        payload = json.loads(text_file.read_text(encoding="utf-8"))
        card_name = payload.get("card_name") or text_file.stem
        if card_filter_set and card_name not in card_filter_set:
            continue

        index_meta = index_map.get(card_name, {})
        chunks = generate_chunks(
            text_path=text_file,
            index_meta=index_meta,
            chunk_size=settings.chunk_token_size,
            overlap=settings.chunk_overlap,
            enable_benefit_regex=settings.enable_benefit_regex,
        )
        if not chunks:
            print(f"Skipping {card_name}: no chunks generated")
            continue

        chunk_file = settings.chunks_dir / f"{slugify(card_name)}.jsonl"
        if not embed_only:
            dump_chunks(chunks, chunk_file)

        if chunks_only:
            continue

        # Filter chunks with valid content before embedding
        valid_chunks = [c for c in chunks if c.content and c.content.strip()]
        if not valid_chunks:
            print(f"Skipping {card_name}: no valid text content to embed")
            continue

        try:
            vectors = embedding_client.embed_texts(
                [chunk.content for chunk in valid_chunks]
            )  # type: ignore[arg-type]
            records = [
                EmbeddingRecord(chunk=chunk, vector=vector)
                for chunk, vector in zip(valid_chunks, vectors)
            ]
            vector_store.upsert(records)  # type: ignore[union-attr]
            print(f"Embedded {len(records)} chunks for {card_name}")
        except Exception as e:
            print(f"Embedding failed for {card_name}: {e}")
