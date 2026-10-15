"""nDCG@10, MRR@10 and Recall@10 from rankings and qrels, and the comparison with the model card.

nDCG uses linear gains (the trec_eval / pytrec_eval convention MTEB scores with);
for SciFact's binary judgments this is the same as exponential gains. Relevant
documents that were not retrieved still count in the ideal DCG.

A pilot over fewer than all 300 test queries estimates the full-split score
with sampling error; ``compare_with_reference`` reports the standard error and
says whether the card's figure lies inside the 95% interval, and calls a
result comparable only for the full split, full corpus and the card's setup.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Sequence

MIN_QUERIES_FOR_INTERVAL = 10   # below this the normal approximation says nothing useful
REFERENCE = {
    "metric": "ndcg_at_10",
    "value": 0.7947,
    "source": "huggingface.co/petegordon/olmo3-embed-7b model card",
    "queries": 300,
    "split": "test",
    "setup": "mteb 2.22-2.24, bf16, LoRA run before merging (the merged model scores 0.7944)",
    "in_domain": "SciFact train qrels were in the training data; test queries and corpus were decontaminated",
}


def ndcg_at_k(ranked: Sequence[str], relevant: Dict[str, int], k: int = 10) -> float:
    dcg = sum(relevant.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def mrr_at_k(ranked: Sequence[str], relevant: Dict[str, int], k: int = 10) -> float:
    for i, d in enumerate(ranked[:k]):
        if relevant.get(d, 0) > 0:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(ranked: Sequence[str], relevant: Dict[str, int], k: int = 10) -> float:
    if not relevant:
        return 0.0
    return sum(1 for d in ranked[:k] if relevant.get(d, 0) > 0) / len(relevant)


def _mean_and_stderr(values: List[float]):
    n = len(values)
    if n == 0:
        return 0.0, None
    mean = sum(values) / n
    if n < 2:
        return mean, None
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var / n)


def evaluate(rankings: Iterable[Dict[str, Any]], qrels: Dict[str, Dict[str, int]], k: int = 10) -> Dict[str, Any]:
    """Per-query and mean metrics. ``rankings`` are dicts with query_id and ranked_doc_ids."""
    per_query: Dict[str, Dict[str, float]] = {}
    for row in rankings:
        qid, ranked = row["query_id"], row["ranked_doc_ids"]
        if qid not in qrels:
            raise ValueError(f"query {qid} has no judgments in the qrels")
        rel = qrels[qid]
        per_query[qid] = {f"ndcg_at_{k}": ndcg_at_k(ranked, rel, k), f"mrr_at_{k}": mrr_at_k(ranked, rel, k),
                          f"recall_at_{k}": recall_at_k(ranked, rel, k)}
    out: Dict[str, Any] = {"k": k, "queries": len(per_query)}
    for name in (f"ndcg_at_{k}", f"mrr_at_{k}", f"recall_at_{k}"):
        mean, se = _mean_and_stderr([m[name] for m in per_query.values()])
        out[name], out[name + "_stderr"] = mean, se
    out["per_query"] = per_query
    return out


def compare_with_reference(metrics: Dict[str, Any], comparable_setup: bool, problems: Sequence[str] = ()) -> Dict[str, Any]:
    """How a measured nDCG@10 relates to the card's 0.7947.

    ``comparable_setup`` is whether the run used the card's model, prompt, dtype,
    the full pinned corpus and top_k >= 10; ``problems`` says why not.
    """
    mean, se, n = metrics.get("ndcg_at_10"), metrics.get("ndcg_at_10_stderr"), metrics.get("queries", 0)
    out: Dict[str, Any] = {"reference": REFERENCE, "measured": mean, "queries": n,
                           "difference": None if mean is None else round(mean - REFERENCE["value"], 4)}
    reasons = list(problems)
    if n != REFERENCE["queries"]:
        reasons.append(f"{n} of the {REFERENCE['queries']} test queries (a pilot estimates the full score "
                       "with sampling error)")
    out["comparable"] = bool(comparable_setup and not reasons)
    out["not_comparable_because"] = reasons
    if mean is not None and se and n >= MIN_QUERIES_FOR_INTERVAL:
        low, high = mean - 1.96 * se, mean + 1.96 * se
        out["ci95"] = [round(low, 4), round(high, 4)]
        out["reference_inside_ci95"] = low <= REFERENCE["value"] <= high
    return out
