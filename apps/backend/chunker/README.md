# Chunker / Embedding Pipeline

이 디렉터리는 크롤러가 수집한 `datasets/` 데이터를 RAG(검색 증강
생성)용 청크와 벡터로 변환하는 모듈입니다. 크롤러가 PDF와 JSON을
생성하면, chunker가 다음 단계를 수행합니다.

1. `datasets/index.csv`를 읽어 카드별 기본 메타데이터(회사, 연회비,
   최소 이용실적, PDF 경로 등)를 확보합니다.
2. `datasets/text/*.json` 파일을 로드하여 카드별 텍스트를 구조화된
   청크로 나눕니다.
   - **Overview Chunk** : 카드 전반 요약/핵심 메타데이터
   - **Benefit Chunk** : 혜택/조건 섹션을 regex/규칙 기반으로 분리
   - **Fallback Chunk** : 위 규칙으로 못 잡은 텍스트는 슬라이딩 윈도우
     방식으로 일정 토큰 크기로 분할
3. 청크는 `datasets/chunks/{card}.jsonl`로 저장되어 재처리가 가능하며,
   각 항목에는 `chunk_id`, `card_name`, `company`, `chunk_type`, `category`
   (혜택 카테고리), `metadata`(연회비, 최소 실적, source URL 등)가 포함됩니다.
4. Upstage Embedding API를 호출하여 청크 내용을 임베딩 벡터로 변환합니다.
5. 로컬 Chroma 벡터 DB(`datasets/embeddings_cache/chroma_db`)에 청크와
   벡터를 upsert하여, 이후 RAG 서비스가 벡터 검색을 수행할 수 있도록
   합니다.

## 디렉터리 구조

```
apps/backend/chunker/
├── __init__.py
├── README.md                   # 현재 문서
├── chunk_models.py             # Chunk/Embedding dataclass 정의
├── chunk_extractor.py          # 텍스트 -> 청크 변환 로직
├── embedding_client.py         # Upstage Embedding API 클라이언트
├── vector_store.py             # Chroma 벡터 스토리지 어댑터
├── pipeline.py                 # end-to-end 실행 파이프라인
├── config.py                   # 경로/환경변수/설정 로더
└── cli.py                      # 커맨드라인 엔트리포인트
```

## 환경 변수 (`apps/backend/.env`)

```
UPSTAGE_API_KEY=...                   # 필수
UPSTAGE_EMBEDDING_MODEL=solar-embedding-1-large  # 선택
CHUNK_TOKEN_SIZE=500                 # 선택 (슬라이딩 윈도우 크기)
CHUNK_OVERLAP=60                     # 선택 (슬라이딩 윈도우 중첩)
ENABLE_BENEFIT_REGEX=true            # 혜택 섹션 감지 토글
```

`config.py`는 `.env`를 자동으로 읽어 경로와 설정을 초기화합니다. 키가
없으면 명확한 오류를 발생시켜 빠르게 문제를 확인할 수 있습니다.

## 실행 방법

크롤링이 완료되어 `datasets/pdfs`, `datasets/text`, `datasets/index.csv`가
채워졌다고 가정합니다.

```bash
# 0) 루트에서 의존성 1회 설치
uv sync

# 1) 전체 카드 대상 청크 + 임베딩 생성
uv run python -m apps.backend.chunker.cli

# 2) 특정 카드만 청크 생성 (임베딩 제외)
uv run python -m apps.backend.chunker.cli \
    --cards "KB Easy Pick 카드" --chunks-only

# 3) 기존에 생성된 청크 jsonl을 임베딩만 재생성
uv run python -m apps.backend.chunker.cli --embed-only
```

CLI 옵션 요약:

| 옵션             | 설명 |
|------------------|------|
| `--cards ...`     | 지정한 카드만 처리 |
| `--chunks-only`   | 청크 파일만 생성 (임베딩 생략) |
| `--embed-only`    | 기존 청크를 재활용하여 임베딩만 수행 |

## 청크 설계

- **Overview Chunk** : 카드 메타데이터, 연회비, PDF 제목 등 핵심 정보를
  bullet 형태로 요약.
- **Benefit Chunk** : `혜택`, `할인`, `%` 등의 키워드/패턴을 기반으로
  섹션을 추출. 카테고리를 추정하여 metadata에 저장.
- **Fallback Chunk** : 혜택 추출에 실패한 텍스트를 슬라이딩 윈도우 방식으로
  분할 (기본 500 토큰, 60 토큰 오버랩)하여 놓침이 없도록 처리.
- 모든 청크는 `chunk_id`(카드 slug + 타입 + 번호)를 가지며, RAG 단계에서
  필터링하기 쉽도록 `company`, `card_name`, `chunk_type`, `category` 메타데이터를 포함.

## 벡터 스토어

- 기본 구현은 로컬 **Chroma**(`datasets/embeddings_cache/chroma_db`)를 사용합니다.
- `vector_store.py`를 통해 추후 Milvus/pgvector 등의 어댑터를 추가할 수 있도록
  추상화되어 있습니다.

## 결과물

- `datasets/chunks/*.jsonl` : 카드별 청크 JSON 라인 파일
- `datasets/embeddings_cache/chroma_db` : Chroma 퍼시스턴스 디렉터리

이후 RAG 서비스는 Chroma를 직접 열거나, 추후 필요 시 다른 벡터 DB로
마이그레이션할 수 있습니다.
