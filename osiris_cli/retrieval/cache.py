"""Resumable on-disk cache of document embeddings.

Embedding 5,183 SciFact abstracts with a 7B model takes minutes on a GPU and
hours on a CPU, so the corpus is embedded in chunks and each chunk is saved as
it completes; an interrupted build resumes at the first missing chunk.

Layout: ``<root>/<key>/fingerprint.json`` plus ``chunk-NNNNN.npy`` (float32,
read with ``allow_pickle=False``) and ``chunk-NNNNN.json`` (the chunk's doc ids
and the SHA-256 of each document's text). ``key`` hashes the embedder
fingerprint (model, resolved revision, dtype, max length, document format), so
another model or revision never reads these vectors. A chunk is reused only if
its ids and text hashes match the documents being indexed now.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from osiris_cli.retrieval.embedder import require, sha256_text

CHUNK_SIZE = 256


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _atomic_write(path: str, write: Callable[[Any], None], mode: str = "wb") -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, mode) as f:
            write(f)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


class EmbeddingCache:
    def __init__(self, root: str):
        self.root = root

    @staticmethod
    def key(fingerprint: Dict[str, Any]) -> str:
        return hashlib.sha256(_canon(fingerprint).encode("utf-8")).hexdigest()[:20]

    def directory(self, fingerprint: Dict[str, Any]) -> str:
        return os.path.join(self.root, self.key(fingerprint))

    def embed(self, fingerprint: Dict[str, Any], doc_ids: Sequence[str], texts: Sequence[str],
              encode: Callable[[List[str]], Any], chunk_size: int = CHUNK_SIZE,
              progress: Optional[Callable[[int, int, int], None]] = None):
        """Embeddings for ``texts`` (one row per doc id, in order), from the cache where it has them.

        ``progress(done, total, encoded_now)`` is called after each chunk.
        Returns (matrix, stats) where stats counts reused and newly encoded documents.
        """
        np = require("numpy")
        if len(doc_ids) != len(texts):
            raise ValueError("doc_ids and texts differ in length")
        where = self.directory(fingerprint)
        os.makedirs(where, exist_ok=True)
        fp_path = os.path.join(where, "fingerprint.json")
        if not os.path.isfile(fp_path):
            _atomic_write(fp_path, lambda f: f.write(json.dumps(fingerprint, indent=2, sort_keys=True)), "w")
        parts, reused, encoded, started = [], 0, 0, time.time()
        for number, start in enumerate(range(0, len(doc_ids), chunk_size)):
            ids = list(doc_ids[start:start + chunk_size])
            chunk_texts = list(texts[start:start + chunk_size])
            meta = {"ids": ids, "text_sha256": [sha256_text(t) for t in chunk_texts]}
            npy = os.path.join(where, f"chunk-{number:05d}.npy")
            meta_path = os.path.join(where, f"chunk-{number:05d}.json")
            vectors = self._load_chunk(npy, meta_path, meta)
            if vectors is None:
                vectors = np.asarray(encode(chunk_texts), dtype=np.float32)
                if vectors.shape[0] != len(ids):
                    raise ValueError(f"encoder returned {vectors.shape[0]} rows for {len(ids)} documents")
                _atomic_write(npy, lambda f: np.save(f, vectors, allow_pickle=False))
                # The metadata is written last: a chunk counts as cached only once both files exist.
                _atomic_write(meta_path, lambda f: f.write(json.dumps(meta)), "w")
                encoded += len(ids)
            else:
                reused += len(ids)
            parts.append(vectors)
            if progress:
                progress(start + len(ids), len(doc_ids), encoded)
        matrix = np.vstack(parts) if parts else np.zeros((0, 0), dtype=np.float32)
        return matrix, {"cache_key": self.key(fingerprint), "reused": reused, "encoded": encoded,
                        "seconds": round(time.time() - started, 3)}

    @staticmethod
    def _load_chunk(npy: str, meta_path: str, expected: Dict[str, List[str]]):
        if not (os.path.isfile(npy) and os.path.isfile(meta_path)):
            return None
        try:
            with open(meta_path, encoding="utf-8") as f:
                if json.load(f) != expected:
                    return None
            np = require("numpy")
            vectors = np.load(npy, allow_pickle=False)
        except (OSError, ValueError):
            return None
        if vectors.ndim != 2 or vectors.shape[0] != len(expected["ids"]):
            return None
        return vectors

    def entries(self) -> List[Dict[str, Any]]:
        """Every cached index: its key, fingerprint and how many documents it holds."""
        out = []
        if not os.path.isdir(self.root):
            return out
        for key in sorted(os.listdir(self.root)):
            fp_path = os.path.join(self.root, key, "fingerprint.json")
            if not os.path.isfile(fp_path):
                continue
            with open(fp_path, encoding="utf-8") as f:
                fingerprint = json.load(f)
            docs = 0
            for name in os.listdir(os.path.join(self.root, key)):
                if name.startswith("chunk-") and name.endswith(".json"):
                    with open(os.path.join(self.root, key, name), encoding="utf-8") as f:
                        docs += len(json.load(f)["ids"])
            out.append({"key": key, "fingerprint": fingerprint, "documents": docs})
        return out
