# 개인 테스트 용 vectordb (개인용, 동재님이 vectordb 개발하시면 그걸로 수정)
import chromadb
from langchain_chroma import Chroma

vectorstore = None  # 전역 vectorstore 인스턴스

def setup_vectorstore(
    underlying_embeddings,
    collection_name="card_disclosures",
    persist_directory="datasets/embeddings_cache/chroma_db",
    documents=None,
):
    """ChromaDB 벡터스토어를 로드하거나 생성합니다. 앱 시작 시 1회 호출."""

    global vectorstore

    # 이미 생성되어 있으면 기존 것 반환
    if vectorstore is not None:
        print("ℹ️ 이미 초기화된 벡터스토어를 반환합니다.")
        return vectorstore

    # documents가 제공된 경우에만 추가
    if documents:
        # 새로 문서를 넣어서 생성 (테스트용)
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=underlying_embeddings,
            collection_name=collection_name,
            persist_directory=persist_directory,
        )
        print(f"✅ {len(documents)}개의 문서가 추가되었습니다.")
    else:
        # 기존 chroma_db 로드 (실제 운영)
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=underlying_embeddings,
            persist_directory=persist_directory,
        )
        print(f"ℹ️ 기존 벡터스토어를 로드했습니다. (collection: {collection_name})")

    return vectorstore


def get_vectorstore():
    """다른 모듈에서 vectorstore를 가져올 때 사용"""
    if vectorstore is None:
        raise RuntimeError(
            "vectorstore가 초기화되지 않았습니다. setup_vectorstore()를 먼저 호출하세요."
        )
    return vectorstore
