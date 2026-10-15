"""Index -> query -> rank: exact cosine search over the embedded corpus.

Vectors are unit length, so the dot product is the cosine similarity. Every
document is scored (5,183 x 4,096 floats is small), and ties are broken by doc
id, so a given set of vectors always yields the same ranking.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from osiris_cli.retrieval.cache import EmbeddingCache
from osiris_cli.retrieval.embedder import require
from osiris_cli.retrieval.scifact import doc_text


@dataclass
class RetrievalResult:
    query_id: str
    ranked_doc_ids: List[str]
    scores: List[float]
    latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RetrievalLoop:
    def __init__(self, embedder: Any, top_k: int = 10):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        self.embedder = embedder
        self.top_k = top_k
        self.doc_ids: List[str] = []
        self.doc_embeddings = None
        self.index_stats: Dict[str, Any] = {}

    def build_index(self, docs: Dict[str, Dict[str, str]], cache: Optional[EmbeddingCache] = None,
                    progress: Optional[Callable[[int, int, int], None]] = None) -> Dict[str, Any]:
        """Embed every document (doc id -> {"title", "text"}), reusing cached chunks."""
        self.doc_ids = sorted(docs)
        texts = [doc_text(docs[d]) for d in self.doc_ids]
        if cache is None:
            started = time.time()
            self.doc_embeddings = self.embedder.encode_documents(texts)
            self.index_stats = {"cache_key": None, "reused": 0, "encoded": len(texts),
                                "seconds": round(time.time() - started, 3)}
        else:
            self.doc_embeddings, self.index_stats = cache.embed(
                self.embedder.fingerprint(), self.doc_ids, texts, self.embedder.encode_documents, progress=progress)
        self.index_stats["documents"] = len(self.doc_ids)
        self.index_stats["dimension"] = int(self.doc_embeddings.shape[1]) if len(self.doc_ids) else 0
        return self.index_stats

    def search(self, query_vector, k: Optional[int] = None):
        np = require("numpy")
        if self.doc_embeddings is None:
            raise RuntimeError("the index is not built")
        k = min(k or self.top_k, len(self.doc_ids))
        scores = self.doc_embeddings @ np.asarray(query_vector, dtype=np.float32)
        order = np.argsort(-scores, kind="stable")[:k]   # doc ids are sorted, so ties go by doc id
        return [self.doc_ids[i] for i in order], [float(scores[i]) for i in order]

    def retrieve(self, query_id: str, query_text: str) -> RetrievalResult:
        started = time.perf_counter()
        vector = self.embedder.encode_queries([query_text])[0]
        ids, scores = self.search(vector)
        return RetrievalResult(query_id, ids, scores, round((time.perf_counter() - started) * 1000.0, 3))

    def run(self, queries: Dict[str, str], query_ids: Sequence[str],
            on_result: Optional[Callable[[RetrievalResult], None]] = None) -> List[RetrievalResult]:
        results = []
        for qid in query_ids:
            result = self.retrieve(qid, queries[qid])
            if on_result:
                on_result(result)
            results.append(result)
        return results
