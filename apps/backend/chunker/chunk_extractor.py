from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chunk_models import Chunk


BENEFIT_KEYWORDS = ["혜택", "할인", "적립", "우대", "%"]


def slugify(value: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z가-힣]+", "-", value).strip("-")
    return value or "chunk"


def generate_chunks(
    text_path: Path,
    index_meta: Dict[str, str],
    chunk_size: int,
    overlap: int,
    enable_benefit_regex: bool,
) -> List[Chunk]:
    payload = json.loads(text_path.read_text(encoding="utf-8"))
    text = payload.get("text") or ""
    if not text.strip():
        return []

    company = payload.get("company") or index_meta.get("company") or "Unknown"
    card_name = (
        payload.get("card_name") or index_meta.get("card_name") or text_path.stem
    )
    base_slug = slugify(card_name)

    chunks: List[Chunk] = []
    overview = _build_overview_chunk(
        base_slug,
        company,
        card_name,
        payload,
        index_meta,
    )
    chunks.append(overview)

    benefit_chunks: List[Chunk] = []
    if enable_benefit_regex:
        benefit_chunks = _extract_benefit_chunks(
            text=text,
            company=company,
            card_name=card_name,
            base_slug=base_slug,
            base_metadata=_base_metadata(payload, index_meta),
        )

    if not benefit_chunks:
        benefit_chunks = _window_chunks(
            text,
            company,
            card_name,
            base_slug,
            _base_metadata(payload, index_meta),
            chunk_size,
            overlap,
        )

    chunks.extend(benefit_chunks)
    return chunks


def _base_metadata(
    payload: Dict[str, Any], index_meta: Dict[str, str]
) -> Dict[str, Any]:
    metadata = {
        "file_size_bytes": payload.get("file_size_bytes"),
        "page_count": payload.get("page_count"),
        "source_url": payload.get("source_url") or index_meta.get("source_url"),
        "local_pdf": payload.get("local_path") or index_meta.get("local_path"),
    }
    for key in ("annual_fee", "min_performance", "benefit_summary"):
        if key in payload:
            metadata[key] = payload[key]
        elif key in index_meta:
            metadata[key] = index_meta[key]
    return {k: v for k, v in metadata.items() if v is not None}


def _build_overview_chunk(
    base_slug: str,
    company: str,
    card_name: str,
    payload: Dict[str, Any],
    index_meta: Dict[str, str],
) -> Chunk:
    metadata = _base_metadata(payload, index_meta)
    bullet_lines = []
    if "annual_fee" in metadata:
        bullet_lines.append(f"- Annual fee: {metadata['annual_fee']}")
    if "min_performance" in metadata:
        bullet_lines.append(f"- Minimum performance: {metadata['min_performance']}")
    if payload.get("pdf_title"):
        bullet_lines.append(f"- PDF title: {payload['pdf_title']}")
    bullet_lines.append(f"- Source URL: {metadata.get('source_url', 'unknown')}")

    overview_text = f"{card_name} ({company}) disclosure overview\n" + "\n".join(
        bullet_lines
    )
    return Chunk(
        chunk_id=f"{base_slug}-overview",
        company=company,
        card_name=card_name,
        chunk_type="overview",
        category=None,
        content=overview_text,
        metadata=metadata,
    )


def _create_chunk(
    content: str,
    company: str,
    card_name: str,
    base_slug: str,
    counter: int,
    base_metadata: Dict[str, Any],
) -> Chunk:
    # Heuristic category inference
    category = _infer_category(content)
    chunk_type = "benefit" if _looks_like_benefit(content) else "fallback"

    return Chunk(
        chunk_id=f"{base_slug}-{chunk_type}-{counter:02d}",
        company=company,
        card_name=card_name,
        chunk_type=chunk_type,
        category=category,
        content=content,
        metadata=base_metadata,
    )


def _extract_benefit_chunks(
    text: str,
    company: str,
    card_name: str,
    base_slug: str,
    base_metadata: Dict[str, Any],
) -> List[Chunk]:
    # More aggressive splitting: normalized newlines + split by any newline sequence
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    sections = [s.strip() for s in re.split(r"\n+", text) if s.strip()]

    chunks: List[Chunk] = []
    counter = 1

    # Accumulate small sections to form coherent chunks, but cut before limit
    current_buffer = []
    current_length = 0
    MAX_CHARS = (
        1000  # Conservative limit (approx 250-500 tokens) to stay well under 4000
    )

    for section in sections:
        # If adding this section exceeds limit, flush buffer
        if current_length + len(section) > MAX_CHARS and current_buffer:
            content = "\n".join(current_buffer)
            # Only create chunk if it looks meaningful or just as a fallback
            chunks.append(
                _create_chunk(
                    content, company, card_name, base_slug, counter, base_metadata
                )
            )
            counter += 1
            current_buffer = []
            current_length = 0

        current_buffer.append(section)
        current_length += len(section)

        # If single section is huge (> MAX_CHARS), force split it using windowing
        if len(section) > MAX_CHARS:
            # Flush current buffer first (it has the huge section now, wait no)
            # Actually, current_buffer HAS the huge section now because we appended it above.
            # But that's wrong if we want to split the huge section.
            # Correction: Handle huge section BEFORE appending to buffer or handle separately.

            # Pop the huge section back out
            current_buffer.pop()
            current_length -= len(section)

            # Flush existing buffer
            if current_buffer:
                content = "\n".join(current_buffer)
                chunks.append(
                    _create_chunk(
                        content, company, card_name, base_slug, counter, base_metadata
                    )
                )
                counter += 1
                current_buffer = []
                current_length = 0

            # Split the huge section using windowing
            sub_chunks = _window_chunks(
                section, company, card_name, base_slug, base_metadata, 500, 60
            )
            for sc in sub_chunks:
                # Rename IDs to fit benefit flow or just append
                sc.chunk_id = f"{base_slug}-benefit-{counter:02d}"  # Use benefit ID for consistency
                chunks.append(sc)
                counter += 1
            continue

    # Flush remaining
    if current_buffer:
        content = "\n".join(current_buffer)
        chunks.append(
            _create_chunk(
                content, company, card_name, base_slug, counter, base_metadata
            )
        )

    return chunks


def _looks_like_benefit(section: str) -> bool:
    lower = section.lower()
    return any(keyword in lower for keyword in [kw.lower() for kw in BENEFIT_KEYWORDS])


def _infer_category(section: str) -> Optional[str]:
    header_match = re.match(r"([A-Za-z가-힣&/ ]{2,40})[:\-]", section.strip())
    if header_match:
        return header_match.group(1).strip()
    return None


def _split_sections(text: str) -> List[str]:
    return [seg.strip() for seg in re.split(r"\n{2,}", text) if seg.strip()]


def _window_chunks(
    text: str,
    company: str,
    card_name: str,
    base_slug: str,
    base_metadata: Dict[str, Any],
    chunk_size: int,
    overlap: int,
) -> List[Chunk]:
    tokens = text.split()
    chunks: List[Chunk] = []
    start = 0
    counter = 1
    while start < len(tokens):
        end = min(len(tokens), start + chunk_size)
        window = " ".join(tokens[start:end]).strip()
        if window:
            chunks.append(
                Chunk(
                    chunk_id=f"{base_slug}-fallback-{counter:02d}",
                    company=company,
                    card_name=card_name,
                    chunk_type="fallback",
                    category=None,
                    content=window,
                    metadata=base_metadata,
                )
            )
            counter += 1
        if end == len(tokens):
            break
        start = max(end - overlap, start + 1)
    return chunks
