"""Embedding adapter for petegordon/olmo3-embed-7b (or any sentence-transformers model).

The model card (huggingface.co/petegordon/olmo3-embed-7b) fixes how it is called:

* queries take a task instruction, ``Instruct: {instruction}\\nQuery: {query}``;
  documents take none;
* the embedding is the last token's final hidden state (the tokenizer appends
  EOS), L2-normalized, 4096 dimensions; inputs are cut at 512 tokens;
* its MTEB scores were measured in bf16 with each task's default MTEB prompt.

The default instruction is MTEB's SciFact prompt, so a SciFact run matches how
the card's 79.47 nDCG@10 was measured. torch and sentence-transformers are
imported only when a model is loaded (``pip install "osiris-cli[retrieval]"``).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Sequence

MODEL_ID = "petegordon/olmo3-embed-7b"
# mteb 2.24, tasks/retrieval/eng/sci_fact_retrieval.py: SciFact's default query prompt.
SCIFACT_INSTRUCTION = "Given a scientific claim, retrieve documents that support or refute the claim"
QUERY_TEMPLATE = "Instruct: {instruction}\nQuery: "
DTYPES = ("bfloat16", "float16", "float32", "auto")


class MissingDependency(ImportError):
    """An optional dependency of the retrieval backend is not installed."""


def require(module: str):
    try:
        return __import__(module)
    except ImportError as e:
        raise MissingDependency(
            f"the retrieval backend needs '{module}': pip install \"osiris-cli[retrieval]\""
        ) from e


def _versions(*modules: str) -> Dict[str, str]:
    found = {}
    for module in modules:
        try:
            found[module] = __import__(module).__version__
        except ImportError:
            pass
    return found


@dataclass(frozen=True)
class EmbedderConfig:
    model_id: str = MODEL_ID
    revision: Optional[str] = None       # a commit SHA pins the weights; None is whatever the Hub has today
    device: Optional[str] = None         # None: cuda when available, else cpu
    dtype: str = "bfloat16"              # the card's scores are bf16
    batch_size: int = 8
    max_length: int = 512
    query_instruction: str = SCIFACT_INSTRUCTION
    query_prompt: Optional[str] = None   # a raw query prefix; overrides the instruction template

    def resolved_query_prompt(self) -> str:
        if self.query_prompt is not None:
            return self.query_prompt
        return QUERY_TEMPLATE.format(instruction=self.query_instruction) if self.query_instruction else ""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class OlmoEmbedder:
    """Encodes queries (with the instruction prompt) and documents (without) to unit vectors."""

    def __init__(self, config: EmbedderConfig = EmbedderConfig(), model: Any = None):
        if config.dtype not in DTYPES:
            raise ValueError(f"dtype must be one of {', '.join(DTYPES)}, not {config.dtype!r}")
        self.config = config
        self._model = model      # tests inject anything with .encode(texts, **kwargs) -> (n, d) array
        self.device = config.device

    @property
    def model(self):
        if self._model is None:
            torch = require("torch")
            require("sentence_transformers")
            from sentence_transformers import SentenceTransformer

            self.device = self.config.device or ("cuda" if torch.cuda.is_available() else "cpu")
            kwargs = {} if self.config.dtype == "auto" else {"dtype": getattr(torch, self.config.dtype)}
            self._model = SentenceTransformer(self.config.model_id, revision=self.config.revision,
                                              device=self.device, model_kwargs=kwargs)
            if self.config.max_length:
                self._model.max_seq_length = self.config.max_length
        return self._model

    def _encode(self, texts: Sequence[str], prompt: str):
        np = require("numpy")
        kwargs = {"prompt": prompt} if prompt else {}
        vectors = self.model.encode(list(texts), batch_size=self.config.batch_size, normalize_embeddings=True,
                                    convert_to_numpy=True, show_progress_bar=False, **kwargs)
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(texts):
            raise ValueError(f"the model returned shape {vectors.shape} for {len(texts)} texts")
        # Normalized in bf16, a vector's norm is off by ~0.1%; renormalized in float32, the dot
        # product is the cosine of the bf16 embeddings, which is what MTEB's cosine scores.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def encode_queries(self, queries: Sequence[str]):
        return self._encode(queries, self.config.resolved_query_prompt())

    def encode_documents(self, documents: Sequence[str]):
        return self._encode(documents, "")

    def environment(self) -> Dict[str, Any]:
        """What was actually loaded: revision, dtype, device, dimension, library versions."""
        model = self._model
        env: Dict[str, Any] = {"model_id": self.config.model_id, "requested_revision": self.config.revision,
                               "resolved_revision": None, "device": self.device, "dtype": self.config.dtype,
                               "max_seq_length": getattr(model, "max_seq_length", None),
                               "embedding_dimension": None}
        try:
            first = model[0]
            inner = getattr(first, "auto_model", None) or getattr(first, "model", None)
            env["resolved_revision"] = getattr(inner.config, "_commit_hash", None)
        except (AttributeError, IndexError, KeyError, TypeError):
            pass
        for name in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
            if hasattr(model, name):
                env["embedding_dimension"] = getattr(model, name)()
                break
        try:
            env["dtype"] = str(next(model.parameters()).dtype).replace("torch.", "")
            env["device"] = str(model.device)
        except (AttributeError, StopIteration, TypeError):
            pass
        env["libraries"] = _versions("sentence_transformers", "transformers", "torch", "numpy")
        return env

    def fingerprint(self) -> Dict[str, Any]:
        """Everything that changes a document embedding; the index cache is keyed on it.

        It is taken after the model loads, so an unpinned revision resolves to the
        commit actually downloaded and a new upload gets a new cache entry.
        """
        self.model  # noqa: B018 - load it, so the revision and dtype are the loaded ones
        env = self.environment()
        return {"model_id": self.config.model_id,
                "revision": env["resolved_revision"] or self.config.revision or "unresolved",
                "dtype": env["dtype"], "max_seq_length": env["max_seq_length"],
                "document_prompt": "", "document_format": "mteb: title + ' ' + text"}

    def config_dict(self) -> Dict[str, Any]:
        return dict(asdict(self.config), query_prompt_used=self.config.resolved_query_prompt())
