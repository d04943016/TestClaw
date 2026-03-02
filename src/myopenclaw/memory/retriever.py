from __future__ import annotations

import json
import hashlib
import math
import os
import re
from collections import Counter
from typing import Any
from urllib import request

from myopenclaw.config import Settings
from myopenclaw.memory.store import MemoryStore


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "using",
    "about",
    "have",
    "has",
    "had",
    "will",
    "would",
    "could",
    "should",
    "your",
    "their",
    "there",
    "what",
    "when",
    "where",
    "which",
    "were",
    "been",
}


def _normalize_vector(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.split(r"\s+", text.lower()):
        token = raw.strip().strip(".,:;!?()[]{}\"'`")
        if len(token) < 3:
            continue
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = [tok for tok in text.lower().split() if tok]
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign

        return _normalize_vector(vec)


class OpenAICompatibleEmbedder:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _endpoint(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        return self.base_url + "/embeddings"

    def _request_batch(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self.model,
            "input": texts,
        }
        req = request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        decoded = json.loads(raw)
        data = decoded.get("data", []) if isinstance(decoded, dict) else []
        if not isinstance(data, list):
            raise RuntimeError(f"Invalid embedding response: {decoded}")

        ordered = sorted(
            [row for row in data if isinstance(row, dict)],
            key=lambda item: int(item.get("index", 0)),
        )
        vectors: list[list[float]] = []
        for row in ordered:
            embedding = row.get("embedding", [])
            if not isinstance(embedding, list):
                embedding = []
            vectors.append(_normalize_vector([float(v) for v in embedding]))

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding batch size mismatch: expected {len(texts)}, got {len(vectors)}"
            )
        return vectors

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            out.extend(self._request_batch(chunk))
        return out


class MemoryRetriever:
    def __init__(self, settings: Settings, store: MemoryStore) -> None:
        self.settings = settings
        self.store = store
        self.hash_embedder = HashingEmbedder(dim=settings.embedding_dim)
        self.semantic_embedder = self._build_semantic_embedder()
        self.semantic_weight = self._safe_float(os.getenv("AGENT_MEMORY_SEMANTIC_WEIGHT", "0.72"), 0.72)
        self.semantic_weight = min(1.0, max(0.0, self.semantic_weight))
        self.embedding_namespace = self._embedding_namespace()

    def _safe_float(self, value: str, fallback: float) -> float:
        try:
            return float(value)
        except Exception:
            return fallback

    def _build_semantic_embedder(self) -> OpenAICompatibleEmbedder | None:
        api_key = os.getenv("AGENT_EMBEDDING_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("AGENT_EMBEDDING_MODEL", "text-embedding-3-small").strip() or "text-embedding-3-small"
        base_url = os.getenv("AGENT_EMBEDDING_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"
        return OpenAICompatibleEmbedder(api_key=api_key, model=model, base_url=base_url)

    def _embedding_namespace(self) -> str:
        if self.semantic_embedder:
            model = re.sub(r"[^a-zA-Z0-9_.-]+", "_", self.semantic_embedder.model)
            return f"agent_semantic::{model}"
        return f"agent_hash::{self.settings.embedding_dim}"

    def _normalize_scores(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        max_score = max(scores)
        min_score = min(scores)
        if abs(max_score - min_score) < 1e-9:
            return [1.0 if max_score > 0 else 0.0 for _ in scores]
        return [(score - min_score) / (max_score - min_score) for score in scores]

    def _bm25_keyword_scores(self, texts: list[str], query_terms: list[str]) -> list[float]:
        if not texts or not query_terms:
            return [0.0 for _ in texts]

        tokenized = [_tokenize(text) for text in texts]
        doc_freq: Counter[str] = Counter()
        doc_lengths = [len(tokens) for tokens in tokenized]
        avg_doc_len = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0

        for tokens in tokenized:
            for token in set(tokens):
                doc_freq[token] += 1

        k1 = 1.5
        b = 0.75
        total_docs = len(tokenized)

        scores: list[float] = []
        for tokens in tokenized:
            tf = Counter(tokens)
            doc_len = max(1, len(tokens))
            score = 0.0
            for term in query_terms:
                freq = tf.get(term, 0)
                if freq <= 0:
                    continue
                df = max(1, doc_freq.get(term, 1))
                idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
                denom = freq + k1 * (1 - b + b * doc_len / max(1.0, avg_doc_len))
                score += idf * ((freq * (k1 + 1)) / max(1e-9, denom))
            scores.append(score)
        return scores

    def _semantic_scores(self, chunks: list[dict[str, Any]], query: str) -> tuple[list[float], str]:
        if self.semantic_embedder:
            try:
                query_vec = self.semantic_embedder.embed_batch([query])[0]
                vectors: list[list[float] | None] = [None for _ in chunks]
                missing_texts: list[str] = []
                missing_indices: list[int] = []

                for idx, chunk in enumerate(chunks):
                    chunk_id = int(chunk["id"])
                    cached = self.store.get_chunk_embedding(
                        chunk_id=chunk_id,
                        namespace=self.embedding_namespace,
                    )
                    if cached:
                        vectors[idx] = cached
                    else:
                        missing_texts.append(str(chunk.get("content", ""))[:7000])
                        missing_indices.append(idx)

                if missing_texts:
                    computed = self.semantic_embedder.embed_batch(missing_texts)
                    for idx, vector in zip(missing_indices, computed):
                        vectors[idx] = vector
                        self.store.upsert_chunk_embedding(
                            chunk_id=int(chunks[idx]["id"]),
                            namespace=self.embedding_namespace,
                            embedding=vector,
                        )

                scores = [_dot(vector or [], query_vec) for vector in vectors]
                return scores, "agent_embedding_api"
            except Exception:
                pass

        query_vec = self.hash_embedder.embed(query)
        scores = [_dot(self.hash_embedder.embed(str(chunk.get("content", ""))), query_vec) for chunk in chunks]
        return scores, "hashing_fallback"

    def search(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        chunks = self.store.get_compressed_chunks(session_id=session_id, level=None)
        if not chunks:
            return []

        texts = [str(chunk.get("content", "")) for chunk in chunks]
        query_terms = _tokenize(query)

        keyword_raw = self._bm25_keyword_scores(texts=texts, query_terms=query_terms)
        keyword_norm = self._normalize_scores(keyword_raw)

        semantic_raw, backend = self._semantic_scores(chunks=chunks, query=query)
        semantic_norm = [min(1.0, max(0.0, (value + 1.0) / 2.0)) for value in semantic_raw]

        if query_terms:
            semantic_weight = self.semantic_weight
            keyword_weight = 1.0 - semantic_weight
        else:
            semantic_weight = 1.0
            keyword_weight = 0.0

        results: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            semantic_score = semantic_norm[idx] if idx < len(semantic_norm) else 0.0
            keyword_score = keyword_norm[idx] if idx < len(keyword_norm) else 0.0
            final_score = semantic_weight * semantic_score + keyword_weight * keyword_score
            results.append(
                {
                    **chunk,
                    "score": float(final_score),
                    "semantic_score": float(semantic_score),
                    "keyword_score": float(keyword_score),
                    "retrieval_backend": backend,
                }
            )

        results.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return results[: max(1, min(top_k, len(results)))]
