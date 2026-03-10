# SmartPick 파이프라인 가이드

## 개요

SmartPick 백엔드는 아래 4단계로 동작합니다.

1. **Crawler**: 카드사 문서(PDF)와 메타데이터 수집
2. **Chunker**: 텍스트를 청크로 분할
3. **Embedding**: 청크를 임베딩하고 Chroma DB에 저장
4. **Agent/API**: RAG 검색 기반 추천 응답 제공

핵심 원칙은 다음과 같습니다.

- 루트에서 `uv sync` 1회 수행
- 루트에서 `uv run python -m ...` 방식으로 실행
- 에이전트 실행 전 데이터 파이프라인 완료

## 설치 필요

- Python 3.12
- `uv`
- Node.js 20+ (프론트 실행 시)

```bash
uv sync
```

`apps/backend/.env` 필수/권장 값:

```env
UPSTAGE_API_KEY=your_upstage_api_key
UPSTAGE_EMBEDDING_MODEL=embedding-query
CORS_ALLOW_ORIGINS=http://localhost:3000
LANGSMITH_API_KEY=your_langsmith_api_key
```

## 단계별 실행

### 1) 크롤링

최초 1회 Playwright 브라우저를 설치합니다.

```bash
uv run playwright install chromium
uv run python -m apps.backend.crawler.main
```

출력 결과:

- `datasets/pdfs`
- `datasets/text`
- `datasets/index.csv`

### 2) 청크/임베딩 파이프라인

```bash
uv run python -m apps.backend.chunker.cli
```

출력 결과:

- `datasets/chunks`
- `datasets/embeddings_cache/chroma_db`

옵션:

```bash
# 특정 카드만 청크 생성
uv run python -m apps.backend.chunker.cli --cards "KB Easy Pick 카드" --chunks-only

# 기존 청크에 대해 임베딩만 재생성
uv run python -m apps.backend.chunker.cli --embed-only
```

### 3) 에이전트 실행

```bash
uv run python -m apps.backend.agent.agent
```

주의: 1), 2) 단계가 끝나지 않으면 검색 품질 저하 또는 빈 결과가 발생할 수 있습니다.

### 4) API 서버 실행

```bash
uv run uvicorn apps.backend.main:app --reload --host 0.0.0.0 --port 8000
```

- 헬스체크: `GET /health`
- 채팅 엔드포인트: `POST /agent/chat`

## 프론트엔드 연동

```bash
cd apps/frontend
npm ci
npm run dev
```

`apps/frontend/.env`:

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Docker 실행

```bash
docker compose up --build
```

- `backend`: 8000 포트
- `frontend`: 3000 포트
- `datasets` 볼륨을 `/app/datasets`에 마운트

## 문제 해결 체크리스트

- import 오류가 나면 스크립트 경로 실행이 아닌지 확인 (`python -m` 사용)
- `UPSTAGE_API_KEY` 누락 여부 확인
- `datasets/index.csv`, `datasets/text`가 생성되었는지 확인
- `datasets/embeddings_cache/chroma_db`가 생성되었는지 확인
