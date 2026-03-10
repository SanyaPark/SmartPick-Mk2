"""
Tool 단독 테스트
================
테스트 내용:
1. ChromaDB 연결 확인 (데이터 존재 여부)
2. retriever 단독 테스트 (검색이 되는지)
3. scorer + ranker 단독 테스트
4. formatter 단독 테스트
5. card_rag_search tool 함수 전체 흐름 테스트

터미널에서 실행 (tools 폴더에서): 
    uv run python -m apps.backend.tools.test_agent
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (UPSTAGE_API_KEY 등)
load_dotenv()


def print_divider(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ============================================================
# 테스트 0: 환경 확인
# ============================================================
def test_env():
    print_divider("테스트 0: 환경 확인")

    api_key = os.environ.get("UPSTAGE_API_KEY", "")
    if api_key:
        print(f"✅ UPSTAGE_API_KEY 설정됨 (길이: {len(api_key)})")
    else:
        print("❌ UPSTAGE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return False

    db_path = Path("datasets/embeddings_cache/chroma_db")
    if db_path.exists():
        print(f"✅ ChromaDB 경로 존재: {db_path}")
    else:
        print(f"❌ ChromaDB 경로 없음: {db_path}")
        print("   먼저 embed_chunked_json.py로 임베딩을 실행하세요.")
        return False

    return True


# ============================================================
# 테스트 1: ChromaDB 연결 + 데이터 확인
# ============================================================
def test_chromadb_connection():
    print_divider("테스트 1: ChromaDB 연결 + 데이터 확인")

    from apps.backend.chunker.vector_store import ChromaVectorStore

    vs = ChromaVectorStore(
        persist_directory=Path("datasets/embeddings_cache/chroma_db"),
        collection_name="card_disclosures",
    )

    count = vs.collection.count()
    print(f"✅ 컬렉션 'card_disclosures' 연결 성공")
    print(f"   총 청크 수: {count}개")

    if count == 0:
        print("❌ 데이터가 없습니다. embed_chunked_json.py를 먼저 실행하세요.")
        return False, None

    # 샘플 데이터 확인
    sample = vs.collection.peek(limit=5)
    print(f"\n📋 샘플 데이터 (상위 5개):")
    
    all_card_names = set()
    all_categories = set()
    all_major_categories = set()
    
    for i, meta in enumerate(sample["metadatas"]):
        print(f"   [{i+1}] card_name: {meta.get('card_name', 'N/A')}")
        print(f"       card_company: {meta.get('card_company', 'N/A')}")
        print(f"       category: {meta.get('category', 'N/A')}")
        print(f"       major_categories: {meta.get('major_categories', 'N/A')}")
        print(f"       min_performance: {meta.get('min_performance', 'N/A')}")
        print(f"       annual_fee: {meta.get('annual_fee', 'N/A')}")
        doc_preview = sample["documents"][i][:80] + "..." if len(sample["documents"][i]) > 80 else sample["documents"][i]
        print(f"       content: {doc_preview}")
        print()
        
        if meta.get("card_name"):
            all_card_names.add(meta["card_name"])
        if meta.get("category"):
            all_categories.add(meta["category"])
        if meta.get("major_categories"):
            all_major_categories.add(meta["major_categories"])

    # 전체 메타데이터 분석 (더 많은 샘플)
    all_sample = vs.collection.peek(limit=100)
    for meta in all_sample["metadatas"]:
        if meta.get("card_name"):
            all_card_names.add(meta["card_name"])
        if meta.get("category"):
            all_categories.add(meta["category"])
        if meta.get("major_categories"):
            all_major_categories.add(meta["major_categories"])

    print(f"📊 발견된 메타데이터 (샘플 기준):")
    print(f"   카드명: {all_card_names}")
    print(f"   카테고리(category): {all_categories}")
    print(f"   주요카테고리(major_categories): {all_major_categories}")

    # 테스트에서 사용할 데이터 반환
    test_data = {
        "card_names": list(all_card_names),
        "categories": list(all_categories),
        "major_categories": list(all_major_categories),
    }
    
    return True, test_data


# ============================================================
# 테스트 2: retriever 단독 테스트
# ============================================================
def test_retriever(test_data: dict):
    print_divider("테스트 2: retriever 단독 테스트")

    from apps.backend.tools.retriever import CardRetriever

    retriever = CardRetriever(
        persist_directory="datasets/embeddings_cache/chroma_db",
        collection_name="card_disclosures"
    )

    # major_categories에서 키워드 추출
    keywords = []
    if test_data.get("major_categories"):
        # "Cultural, Shopping" 형태에서 개별 키워드 추출
        for mc in test_data["major_categories"]:
            keywords.extend([k.strip() for k in mc.split(",")])
        keywords = list(set(keywords))[:3]  # 중복 제거 후 3개만
    
    if not keywords:
        keywords = ["Shopping"]  # 기본값

    print(f"🔍 search() 테스트")
    print(f"   query: '커피 할인 혜택'")
    print(f"   budget_filter: 1000000")
    print(f"   category_filter: {keywords}")

    try:
        results = retriever.search(
            query="커피 할인 혜택",
            budget_filter=1000000,
            category_filter=keywords
        )

        print(f"\n   검색 결과: {len(results)}건")

        if results:
            print(f"\n   📋 검색 결과 상세:")
            for i, result in enumerate(results[:5]):  # 상위 5개만 출력
                meta = result.get("metadata", {})
                print(f"   [{i+1}] card_name: {meta.get('card_name')}")
                print(f"       category: {meta.get('category', 'N/A')}")
                print(f"       distance: {result.get('distance', 'N/A'):.4f}")
                content_preview = result.get("content", "")[:80] + "..."
                print(f"       content: {content_preview}")
                print()
        else:
            print("   ⚠️ 검색 결과가 없습니다. 필터 조건을 확인하세요.")

    except Exception as e:
        print(f"   ❌ 검색 실패: {e}")
        return None

    # get_full_card_info 테스트
    if test_data.get("card_names"):
        test_card = test_data["card_names"][0]
        print(f"\n🔍 get_full_card_info() 테스트 (카드: {test_card})")

        try:
            card_info = retriever.get_full_card_info([test_card])
            chunk_count = len(card_info.get(test_card, []))
            print(f"   '{test_card}'의 전체 청크: {chunk_count}건")

            if chunk_count > 0:
                print(f"   첫 번째 청크 메타데이터:")
                first_chunk = card_info[test_card][0]
                meta = first_chunk.get("metadata", {})
                for key, value in meta.items():
                    print(f"       {key}: {value}")

        except Exception as e:
            print(f"   ❌ 카드 정보 조회 실패: {e}")

    return results


# ============================================================
# 테스트 3: scorer + ranker 테스트
# ============================================================
def test_scorer_ranker():
    print_divider("테스트 3: scorer + ranker 테스트")

    from apps.backend.tools.scorer import CardScorer
    from apps.backend.tools.ranker import CardRanker

    scorer = CardScorer()
    ranker = CardRanker()

    # 가짜 검색 결과 (retriever.search() 반환 형태)
    mock_results = [
        {"id": "1", "content": "스타벅스 10% 할인", "metadata": {"card_name": "현대카드 X"}, "distance": 0.1},
        {"id": "2", "content": "전 가맹점 1% 할인", "metadata": {"card_name": "현대카드 X"}, "distance": 0.2},
        {"id": "3", "content": "커피 전문점 15% 할인", "metadata": {"card_name": "신한카드 Mr.Life"}, "distance": 0.15},
        {"id": "4", "content": "편의점 10% 할인", "metadata": {"card_name": "현대카드 X"}, "distance": 0.25},
        {"id": "5", "content": "대중교통 5% 할인", "metadata": {"card_name": "신한카드 Mr.Life"}, "distance": 0.3},
        {"id": "6", "content": "마트 5% 할인", "metadata": {"card_name": "KB국민 My WE:SH"}, "distance": 0.35},
    ]

    # scorer 테스트
    scores = scorer.calculate_scores(mock_results)
    print(f"✅ CardScorer.calculate_scores() 결과:")
    for card in scores:
        print(f"   {card['card_name']}: {card['score']}점")

    # ranker 테스트
    ranked = ranker.rank(scores)
    print(f"\n✅ CardRanker.rank() 결과 (정렬 후):")
    for i, card in enumerate(ranked, 1):
        print(f"   {i}위: {card['card_name']} ({card['score']}점)")

    return ranked


# ============================================================
# 테스트 4: formatter 테스트
# ============================================================
def test_formatter():
    print_divider("테스트 4: formatter 테스트")

    from apps.backend.tools.formatter import CardFormatter

    formatter = CardFormatter()

    # 가짜 카드 데이터 (retriever.get_full_card_info() 반환 형태)
    mock_card_data = {
        "현대카드 X": [
            {
                "id": "1",
                "content": "전월 실적 50만원 이상 시...",
                "metadata": {
                    "card_name": "현대카드 X",
                    "card_company": "현대카드",
                    "annual_fee": 50000,
                    "min_performance": 500000,
                    "major_categories": "General, Travel, Life",
                    "benefits_summary": "전 가맹점 1% 할인, 공항 라운지 무료",
                    "category": "전 가맹점 할인",
                    "content": "전월 실적 50만원 이상 시 국내외 모든 가맹점에서 1% 청구 할인",
                    "conditions": "전월 이용 금액 50만원 이상 시 제공"
                }
            },
            {
                "id": "2",
                "content": "공항 라운지 무료 이용",
                "metadata": {
                    "card_name": "현대카드 X",
                    "card_company": "현대카드",
                    "annual_fee": 50000,
                    "min_performance": 500000,
                    "major_categories": "General, Travel, Life",
                    "benefits_summary": "전 가맹점 1% 할인, 공항 라운지 무료",
                    "category": "여행 서비스",
                    "content": "인천국제공항 라운지 무료 이용",
                    "conditions": "연 2회 한도"
                }
            }
        ],
        "신한카드 Mr.Life": [
            {
                "id": "3",
                "content": "커피 전문점 할인",
                "metadata": {
                    "card_name": "신한카드 Mr.Life",
                    "card_company": "신한카드",
                    "annual_fee": 15000,
                    "min_performance": 300000,
                    "major_categories": "Life, Shopping, Coffee",
                    "benefits_summary": "생활 밀착형 할인 카드",
                    "category": "카페",
                    "content": "스타벅스, 투썸플레이스 등 커피 전문점 10% 할인",
                    "conditions": "월 5회, 회당 1천원 한도"
                }
            }
        ]
    }

    results = formatter.format(mock_card_data)

    print(f"✅ CardFormatter.format() 결과: {len(results)}개 카드")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    return results


# ============================================================
# 테스트 5: card_rag_search tool 전체 흐름 테스트
# ============================================================
def test_full_tool(test_data: dict):
    print_divider("테스트 5: card_rag_search tool 전체 흐름 테스트")

    from apps.backend.tools.rag_search import card_rag_search

    # major_categories에서 키워드 추출
    keywords = []
    if test_data.get("major_categories"):
        for mc in test_data["major_categories"]:
            keywords.extend([k.strip() for k in mc.split(",")])
        keywords = list(set(keywords))[:3]
    
    if not keywords:
        keywords = ["Shopping"]

    print(f"🔧 card_rag_search.invoke() 호출")
    print(f"   query: '커피 할인 혜택이 좋은 카드 추천해줘'")
    print(f"   keywords: {keywords}")
    print(f"   budget_filter: 1000000")

    try:
        result = card_rag_search.invoke({
            "query": "커피 할인 혜택이 좋은 카드 추천해줘",
            "keywords": keywords,
            "budget_filter": 1000000,
        })

        print(f"\n✅ tool 반환 결과: {len(result)}개 카드")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        return result

    except Exception as e:
        print(f"❌ tool 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# 메인 실행
# ============================================================
if __name__ == "__main__":
    print("🚀 SmartPick RAG Tool 테스트 시작\n")

    # 테스트 0: 환경 확인
    if not test_env():
        print("\n❌ 환경 설정이 올바르지 않습니다. 종료합니다.")
        exit(1)

    # 테스트 1: ChromaDB 연결
    success, test_data = test_chromadb_connection()
    if not success:
        print("\n❌ ChromaDB 연결 실패. 종료합니다.")
        exit(1)

    # 테스트 2: retriever (실제 데이터)
    test_retriever(test_data)

    # 테스트 3: scorer + ranker (가짜 데이터)
    test_scorer_ranker()

    # 테스트 4: formatter (가짜 데이터)
    test_formatter()

    # 테스트 5: tool 전체 흐름 (실제 데이터)
    test_full_tool(test_data)

    print_divider("테스트 완료 ✅")
