from __future__ import annotations

import time
from typing import Iterable, List

import requests


class UpstageEmbeddingClient:
    def __init__(
        self, api_key: str, model: str = "solar-embedding-1-large-passage", batch_size: int = 32
    ):
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        self.base_url = "https://api.upstage.ai/v1/embeddings"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Filter out empty or whitespace-only strings
        non_empty_texts = [t for t in texts if t and t.strip()]
        if not non_empty_texts:
            return []

        vectors: List[List[float]] = []
        for start in range(0, len(non_empty_texts), self.batch_size):
            batch = non_empty_texts[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": batch}
        for delay in (1, 2, 4, 8):
            response = self.session.post(self.base_url, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json().get("data", [])
                return [item.get("embedding", []) for item in data]
            if response.status_code == 429:
                time.sleep(delay)
                continue
            if response.status_code != 200:
                print(f"Upstage API Error: {response.status_code} - {response.text}")
            response.raise_for_status()
        raise RuntimeError("Failed to obtain embeddings from Upstage after retries")
