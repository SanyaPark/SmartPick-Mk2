"""
벡터 DB 필터링 및 검색 담당

역할:
1. budget_filter로 min_performance 필터링 (ChromaDB where 절)
2. category_filter(keywords)로 major_categories 필터링 (Python 후처리)
3. query를 임베딩하여 content와 유사도 검색
4. card_name으로 전체 혜택 검색
"""

import os
import json
import ast
from pathlib import Path
from typing import List, Optional, Dict, Any

from apps.backend.chunker.embedding_client import UpstageEmbeddingClient
from apps.backend.chunker.vector_store import ChromaVectorStore

# UpstageEmbeddingClient = None
# ChromaVectorStore = None


class CardRetriever:
    """카드 정보 검색기"""

    def __init__(
        self,
        persist_directory: str = "datasets/embeddings_cache/chroma_db",
        collection_name: str = "card_disclosures",
    ):
        """
        Args:
            persist_directory: ChromaDB 저장 경로
            collection_name: 컬렉션 이름
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name

        # 임베딩 클라이언트 초기화
        api_key = os.environ.get("UPSTAGE_API_KEY", "")
        self.embedding_client = UpstageEmbeddingClient(api_key=api_key)

        # 벡터 스토어 초기화
        self.vector_store = ChromaVectorStore(
            persist_directory=self.persist_directory,
            collection_name=self.collection_name,
        )

    def _parse_min_performance(self, value: Any) -> Optional[int]:
        """min_performance 값을 정수로 정규화합니다."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return int(value)

        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            cleaned = cleaned.replace("원", "")
            if cleaned.isdigit():
                return int(cleaned)

        return None

    def _parse_major_categories(self, major_categories: Any) -> set[str]:
        """major_categories를 소문자 카테고리 집합으로 정규화합니다."""
        if major_categories is None:
            return set()

        if isinstance(major_categories, (list, tuple, set)):
            return {
                str(cat).strip().lower() for cat in major_categories if str(cat).strip()
            }

        if not isinstance(major_categories, str):
            return set()

        raw = major_categories.strip()
        if not raw or raw == "N/A":
            return set()

        parsed_list: Optional[List[Any]] = None

        if raw.startswith("[") and raw.endswith("]"):
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    parsed_list = loaded
            except json.JSONDecodeError:
                try:
                    loaded = ast.literal_eval(raw)
                    if isinstance(loaded, list):
                        parsed_list = loaded
                except (SyntaxError, ValueError):
                    parsed_list = None

        if parsed_list is not None:
            return {
                str(cat).strip().strip("\"'").lower()
                for cat in parsed_list
                if str(cat).strip()
            }

        return {
            part.strip().strip("\"'[]").lower()
            for part in raw.split(",")
            if part.strip().strip("\"'[]")
        }

    def _matches_category_filter(
        self, major_categories: str, category_filter: List[str]
    ) -> bool:
        """
        major_categories 문자열이 category_filter 중 하나라도 포함하는지 확인

        Args:
            major_categories: "General,Shopping,Coffee" 형태의 쉼표 구분 문자열
            category_filter: ["Coffee", "Cultural"] 형태의 리스트

        Returns:
            카테고리 필터가 비어있거나, 하나라도 매칭되면 True
        """
        # 필터가 없으면 모두 통과
        if not category_filter:
            return True

        db_categories = self._parse_major_categories(major_categories)

        # major_categories가 없으면 통과 (overview 청크 등)
        if not db_categories:
            return True

        filter_categories = set(kw.lower() for kw in category_filter)

        # 교집합이 있으면 True (OR 조건: 하나라도 매칭되면 OK)
        return bool(db_categories & filter_categories)

    def search(
        self,
        query: str,
        budget_filter: int,
        category_filter: List[str],
        top_k: int = 10,
        pre_filter_k: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        필터링 + 유사도 검색 수행

        처리 순서:
        1. 쿼리 임베딩 생성
        2. ChromaDB에서 min_performance 필터 + 유사도 검색 (pre_filter_k개)
        3. Python에서 major_categories 후처리 필터링
        4. 상위 top_k개 반환

        Args:
            query: 검색 쿼리 (사용자의 카드 혜택 관련 질문)
            budget_filter: 예산 필터 (min_performance 기준, 필수)
            category_filter: 카테고리 필터 (major_categories 기준)
            top_k: 최종 반환할 결과 수 (기본값: 10)
            pre_filter_k: ChromaDB에서 먼저 가져올 결과 수 (기본값: 50)

        Returns:
            검색된 청크 리스트 (메타데이터 포함)
        """

        # Step 1: 쿼리 임베딩 생성
        query_embeddings = self.embedding_client.embed_texts([query])
        if not query_embeddings:
            return []
        query_vector = query_embeddings[0]

        # Step 2: ChromaDB 검색 수행
        # 후처리 필터링을 고려하여 더 많은 결과를 먼저 가져옴
        try:
            results = self.vector_store.collection.query(
                query_embeddings=[query_vector],
                n_results=pre_filter_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            print(f"ChromaDB 검색 오류: {e}")
            return []

        # Step 3: 결과 정리 + 예산/카테고리 후처리 필터링
        search_results = []

        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for i, doc_id in enumerate(ids):
                metadata = metadatas[i] if i < len(metadatas) else {}

                # 예산 후처리 필터링
                min_performance = self._parse_min_performance(
                    metadata.get("min_performance")
                )
                if min_performance is not None and min_performance > budget_filter:
                    continue

                # 카테고리 후처리 필터링
                major_cats = metadata.get("major_categories", "")
                if not self._matches_category_filter(major_cats, category_filter):
                    continue

                result = {
                    "id": doc_id,
                    "content": documents[i] if i < len(documents) else "",
                    "metadata": metadata,
                    "distance": distances[i] if i < len(distances) else 0.0,
                }
                search_results.append(result)

                # top_k개 도달하면 조기 종료
                if len(search_results) >= top_k:
                    break

        return search_results

    def get_full_card_info(
        self, card_names: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        특정 카드들의 전체 혜택 정보 검색

        Args:
            card_names: 검색할 카드 이름 리스트

        Returns:
            {card_name: [혜택 청크들]} 형태의 딕셔너리
        """
        card_data = {}

        for card_name in card_names:
            try:
                # card_name으로 필터링하여 해당 카드의 모든 청크 검색
                results = self.vector_store.collection.get(
                    where={"card_name": {"$eq": card_name}},
                    include=["documents", "metadatas"],
                )

                if results and results.get("ids"):
                    chunks = []
                    ids = results["ids"]
                    documents = results.get("documents", [])
                    metadatas = results.get("metadatas", [])

                    for i, doc_id in enumerate(ids):
                        chunk = {
                            "id": doc_id,
                            "content": documents[i] if i < len(documents) else "",
                            "metadata": metadatas[i] if i < len(metadatas) else {},
                        }
                        chunks.append(chunk)

                    card_data[card_name] = chunks
                else:
                    card_data[card_name] = []

            except Exception as e:
                print(f"카드 정보 검색 오류 ({card_name}): {e}")
                card_data[card_name] = []

        return card_data


# 테스트용 실행
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    retriever = CardRetriever()

    print("=" * 60)
    print("  CardRetriever 단독 테스트")
    print("=" * 60)

    # 테스트 1: 기본 검색
    print("\n🔍 테스트 1: 기본 검색")
    print("   query: '커피 할인'")
    print("   budget_filter: 500000")
    print("   category_filter: ['Coffee', 'Shopping']")

    results = retriever.search(
        query="커피 할인",
        budget_filter=500000,
        category_filter=["Coffee", "Shopping"],
    )

    print(f"\n   검색 결과: {len(results)}개")
    for r in results[:5]:
        card_name = r["metadata"].get("card_name", "Unknown")
        major_cats = r["metadata"].get("major_categories", "N/A")
        print(f"   - {card_name}")
        print(f"     major_categories: {major_cats}")
        print(f"     content: {r['content'][:80]}...")

    # 테스트 2: 카테고리 없이 검색 (budget만)
    print("\n" + "=" * 60)
    print("🔍 테스트 2: 카테고리 필터 없이 검색")
    print("   query: '전 가맹점 할인'")
    print("   budget_filter: 1000000")
    print("   category_filter: []")

    results2 = retriever.search(
        query="전 가맹점 할인",
        budget_filter=1000000,
        category_filter=[],
    )

    print(f"\n   검색 결과: {len(results2)}개")
    for r in results2[:5]:
        card_name = r["metadata"].get("card_name", "Unknown")
        min_perf = r["metadata"].get("min_performance", "N/A")
        print(f"   - {card_name} (min_performance: {min_perf})")

    # 테스트 3: 전체 카드 정보 검색
    print("\n" + "=" * 60)
    print("🔍 테스트 3: 전체 카드 정보 검색")

    if results:
        test_card = results[0]["metadata"].get("card_name", "")
        if test_card:
            print(f"   카드: {test_card}")
            full_info = retriever.get_full_card_info([test_card])
            chunks = full_info.get(test_card, [])
            print(f"   전체 청크 수: {len(chunks)}개")
            for chunk in chunks[:3]:
                category = chunk["metadata"].get("category", "N/A")
                print(f"   - category: {category}")

    print("\n" + "=" * 60)
    print("  테스트 완료")
    print("=" * 60)
