# SmartPick-Mk2 백엔드 데이터베이스 가이드

이 문서는 SmartPick-Mk2 백엔드 환경에서 다른 팀원들이 Supabase 데이터베이스 패턴을 이해하고, CRUD 쿼리와 RAG 스토리지 연동(Markdown) 코드를 쉽게 작성할 수 있도록 만든 레퍼런스 가이드입니다.

---

## 1. 전역 설정 및 핵심 모듈 (`database.py`)
모든 DB 작업은 `apps.backend.core.database` 모듈을 통해 일원화되어 있습니다. 
Supabase 클라이언트를 매번 생성하지 않고 싱글톤(Singleton)으로 가져와서 사용합니다.

```python
from apps.backend.core.database import get_supabase

# FastAPI 라우터나 Agent 함수 내에서
supabase = get_supabase()
```

---

## 2. 쿼리 실행 패턴 (CRUD)

### 2.1. 데이터 읽기 (SELECT)
Supabase Python Client의 `select` 메서드와 `eq()` 같은 필터 메서드를 체이닝하여 사용합니다.

```python
# 1. 단일 조건 검색하여 여러 건 가져오기 (List 반환)
response = supabase.table("user_spending_preferences").select("*").eq("user_id", "유저UUID").execute()

if response.data:
    for row in response.data:
        print(row["category_name"], row["spending_amount"])

# 2. 특정 레코드 딱 1개만 조회하기 (.single() 사용)
# ID 고유 번호 등 무조건 1개만 존재하는 확실한 쿼리에만 사용하세요!
card = supabase.table("cards").select("card_name, manual_file_path").eq("id", "카드UUID").single().execute()

print(card.data["card_name"])
```

### 2.2. 데이터 저장 (INSERT)
새로운 레코드를 입력할 때는 `insert` 메서드를 사용합니다. 배열(List) 안에 딕셔너리(Dict)를 묶어서 넘기면 다중 Insert(Bulk)도 매우 빠르게 작동합니다.

```python
# 다중 데이터 한 번에 삽입 (권장 패턴)
bulk_inserts = [
    {"user_id": "유저UUID", "category_name": "교통", "spending_amount": 100000},
    {"user_id": "유저UUID", "category_name": "쇼핑", "spending_amount": 50000}
]
supabase.table("user_spending_preferences").insert(bulk_inserts).execute()

# 단일 데이터 삽입
insert_data = {"user_id": "유저UUID", "card_id": "카드UUID"}
supabase.table("user_owned_cards").insert(insert_data).execute()
```

### 2.3. 데이터 수정 및 덮어쓰기 (UPDATE / UPSERT)
기존 데이터를 명시적으로 덮어쓰거나(`update`), 없으면 만들고 있으면 통째로 덮어쓰는(`upsert`) 쿼리입니다.

```python
# 조건부 업데이트 (특정 컬럼만 수정할 때)
supabase.table("user_profiles").update({"nickname": "새로운바비"}).eq("id", "유저UUID").execute()

# 통째로 덮어쓰기 (Upsert - id 기반 병합)
supabase.table("user_profiles").upsert({
    "id": "유저UUID", 
    "total_monthly_spending": 600000
}).execute()
```

### 2.4. 데이터 지우기 (DELETE)
조건에 맞는 데이터를 깔끔하게 삭제합니다. `ON DELETE CASCADE` 외래키(Foreign Key) 설정에 따라 자식 테이블 데이터도 같이 쪼르르 지워질 수 있습니다.

```python
# 해당 유저의 모든 기존 선호도 지우고 초기화할 때 유용함
supabase.table("user_spending_preferences").delete().eq("user_id", "유저UUID").execute()
```

---

## 3. Storage(S3) 버킷 마크다운 원본 읽어오기 (RAG)
LLM에게 혜택 정보(RAG)를 먹이기 위해 원본 마크다운 문서(.md)를 읽어와야 할 때, 복잡한 파이썬 스크립트 없이 단 1줄의 전용 헬퍼 함수를 쓰면 됩니다.

```python
from apps.backend.core.database import fetch_markdown_from_s3

file_path = "manual/hyundai_DigitalLover.md"

# S3에서 파일을 다운받아 UTF-8 파이썬 문자열(text)로 뱉어냅니다.
markdown_text = fetch_markdown_from_s3(file_path)

if markdown_text:
    print("마크다운 컨텐츠 도착 완료! 즉시 LLM 프롬프트 Context로 주입 가능.")
```

---

## 4. 예외 처리 가이드 (Best Practice)
DB 쿼리를 날릴 때는 항상 네트워크 장애나 외래키(FK/UUID Format) 오류가 터질 확률이 있습니다. 
FastAPI 라우터에서는 아래처럼 **무조건 `try-except` 블록으로 감싸서** 에러가 백엔드 전체를 터뜨리지 않고 클라이언트(프론트엔드)로 우아하게 `500` 혹은 `400` 에러 코드로 날아가게 해주세요.

```python
from fastapi import HTTPException

try:
    response = supabase.table("users_table_not_exist").select("*").execute()
except Exception as e:
    # 에러 메시지를 까서 클라이언트에 친절하게 전달!
    raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
```
