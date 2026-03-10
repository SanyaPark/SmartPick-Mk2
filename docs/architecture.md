# SmartPick 아키텍처

## 1. 목적

SmartPick은 사용자의 소비 패턴과 예산을 기반으로 신용카드를 추천하는 시스템입니다.
데이터 수집부터 검색/추천 응답까지 하나의 파이프라인으로 연결되어 있습니다.

## 2. 상위 구조

- `apps/backend/crawler`: 카드사 문서 수집(PDF, 메타데이터)
- `apps/backend/chunker`: 문서 청킹 및 임베딩 생성
- `apps/backend/tools`: RAG 검색/점수화/정렬/포맷팅 도구
- `apps/backend/agent`: LangGraph 기반 대화형 추천 에이전트
- `apps/backend/api`: 에이전트를 HTTP API로 노출
- `apps/frontend`: 사용자 채팅 UI
- `datasets`: 수집/가공/임베딩 데이터 저장소

## 3. 실행 아키텍처

### 의존성/실행 표준

- 단일 의존성 정의: 루트 `pyproject.toml`
- 단일 lockfile: 루트 `uv.lock`
- 루트에서 모듈 실행: `uv run python -m apps.backend...`

이 표준을 쓰는 이유는 경로 기준 불일치로 인한 import 오류를 방지하기 위해서입니다.

### 환경 변수

백엔드 환경 변수 파일 위치는 `apps/backend/.env`입니다.

필수:

- `UPSTAGE_API_KEY`

주요 선택값:

- `UPSTAGE_EMBEDDING_MODEL`
- `CORS_ALLOW_ORIGINS`
- `LANGSMITH_API_KEY`

## 4. 데이터 흐름

### 단계 A: 수집 (Crawler)

`apps/backend/crawler`가 카드사 페이지에서 PDF를 수집하고 텍스트를 추출합니다.

출력:

- `datasets/pdfs`
- `datasets/text`
- `datasets/index.csv`

### 단계 B: 가공/임베딩 (Chunker)

`apps/backend/chunker`가 수집 데이터를 읽어 청크를 만들고 임베딩을 생성해 Chroma에 저장합니다.

출력:

- `datasets/chunks`
- `datasets/embeddings_cache/chroma_db`

### 단계 C: 검색/추천 (RAG Tools + Agent)

1. Agent가 사용자 입력에서 예산/카테고리를 구조화
2. `card_rag_search`가 벡터 DB 검색
3. scorer/ranker/formatter로 결과 정제
4. Agent가 최종 답변 생성

### 단계 D: 서비스 (API/Frontend)

- FastAPI가 `/agent/chat`으로 에이전트 결과 제공
- 프론트엔드가 API를 호출해 대화 UI에 표시

## 5. 컴포넌트 책임 분리

- **Crawler**: 외부 데이터 수집 책임
- **Chunker**: 데이터 전처리/벡터화 책임
- **Tools(RAG)**: 검색 및 랭킹 로직 책임
- **Agent**: 대화 흐름/조건 추출/응답 생성 책임
- **API**: 네트워크 인터페이스 책임
- **Frontend**: 사용자 상호작용 책임

## 6. 운영 시퀀스 (권장)

```bash
# 0) 의존성 설치
uv sync

# 1) 수집
uv run playwright install chromium
uv run python -m apps.backend.crawler.main

# 2) 청크/임베딩
uv run python -m apps.backend.chunker.cli

# 3) 에이전트 테스트
uv run python -m apps.backend.agent.agent

# 4) API 서비스
uv run uvicorn apps.backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 7. Troubleshooting

1. `ModuleNotFoundError`
   - 원인: 스크립트 경로 직접 실행
   - 해결: 루트에서 `python -m` 실행

2. 에이전트 결과가 비거나 품질이 낮음
   - 원인: 파이프라인 미실행(특히 임베딩 단계)
   - 해결: 크롤링 + chunker 단계를 먼저 완료

3. 외부 API 오류
   - 원인: `UPSTAGE_API_KEY` 누락/오류
   - 해결: `apps/backend/.env` 값 확인