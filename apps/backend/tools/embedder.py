# 임베딩 모델 초기화 (개인용, 동재님이 embedding 개발하시면 그걸로 수정)
from langchain_upstage import UpstageEmbeddings

underlying_embeddings = UpstageEmbeddings(
    model="solar-embedding-1-large"
)

# --- 참고 코드: 쿼리 임베딩 사용 예시 ---
# query_embedding = underlying_embeddings.embed_query("커피 혜택이 좋은 카드")
