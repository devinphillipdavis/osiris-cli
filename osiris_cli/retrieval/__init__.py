"""Embedding retrieval as an evidence backend: petegordon/olmo3-embed-7b over BEIR SciFact.

    embedder.py        the model adapter (instruction prompt on queries only)
    scifact.py         download and load mteb/scifact at the revision mteb pins
    cache.py           resumable on-disk document embeddings
    retrieval_loop.py  index -> query -> ranked doc ids with scores
    metrics.py         nDCG@10, MRR@10, Recall@10, comparison with the model card
    evidence.py        hash-chained ledger and verifiable evidence capsules
    policy.py          where the 7B model may run (off on Termux by default)
    commands.py        `/retrieval ...` and `osiris retrieval ...`

The boundary: retrieval supplies ranked evidence candidates and records how it
got them (query, instruction, model revision, rankings, scores, metrics). It
does not decide whether a claim is true, and it never writes to the claims
register, facts, notes or training data; promoting a claim stays with OSIRIS's
verification and governance code. It is separate from the chat mentors and
from NCLM training.

torch and sentence-transformers load only when a model does:
``pip install "osiris-cli[retrieval]"``.
"""

from osiris_cli.retrieval.commands import main, run_command

__all__ = ["main", "run_command"]
