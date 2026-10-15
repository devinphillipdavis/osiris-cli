"""BEIR SciFact: download, load and normalize (standard library only).

Reads the BEIR layout -- ``corpus.jsonl``, ``queries.jsonl``, ``qrels/<split>.tsv``
-- from the ``mteb/scifact`` dataset repo at the revision mteb 2.24's SciFact task
pins, so a run uses the same files as the MTEB score it is compared with. That
split has 5,183 abstracts and 300 judged test claims (339 relevant pairs, all
score 1).

``queries.jsonl`` also holds the train claims; only queries judged in the split's
qrels are returned, as in MTEB. Documents are formatted as MTEB formats them:
``title + " " + text`` (stripped), or the text alone when there is no title.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List

REPO = "mteb/scifact"
REVISION = "d56462d0e63a25450459c4f213e49ffdb866f7f9"     # mteb 2.24: SciFact task metadata
DATASET_URL = "https://huggingface.co/datasets/{repo}/resolve/{revision}/{path}"
SOURCE_FILE = "SOURCE.json"
# The pinned revision as the Hub lists it, and mteb's descriptive statistics for its test split.
EXPECTED_BYTES = {"corpus.jsonl": 8023638, "queries.jsonl": 129085, "qrels/test.tsv": 5389}
EXPECTED_COUNTS = {"documents": 5183, "queries": 300, "relevant_pairs": 339}


class DatasetError(RuntimeError):
    """The dataset is missing, malformed or could not be downloaded."""


def split_files(split: str = "test") -> List[str]:
    return ["corpus.jsonl", "queries.jsonl", f"qrels/{split}.tsv"]


@dataclass
class SciFactData:
    corpus: Dict[str, Dict[str, str]]       # doc id -> {"title", "text"}
    queries: Dict[str, str]                 # judged queries of the split only
    qrels: Dict[str, Dict[str, int]]        # query id -> {doc id: grade > 0}
    split: str = "test"
    queries_in_file: int = 0
    source: Dict[str, Any] = field(default_factory=dict)
    files: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def query_ids(self) -> List[str]:
        """Judged query ids in a fixed order (numeric ids numerically): what "the first N" means."""
        return sorted(self.queries, key=lambda q: (0, int(q), "") if q.isdigit() else (1, 0, q))


def doc_text(doc: Dict[str, str]) -> str:
    """A document as mteb embeds it (mteb/_create_dataloaders.py)."""
    title = doc.get("title") or ""
    return (title + " " + doc["text"]).strip() if title else doc["text"]


def file_digests(data_dir: str, split: str = "test") -> Dict[str, Dict[str, Any]]:
    """SHA-256 and size of each of the split's files present in ``data_dir``."""
    digests: Dict[str, Dict[str, Any]] = {}
    for rel in split_files(split):
        path = os.path.join(data_dir, rel)
        if not os.path.isfile(path):
            continue
        sha, size = hashlib.sha256(), 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)
                size += len(chunk)
        digests[rel] = {"sha256": sha.hexdigest(), "bytes": size}
    return digests


def _jsonl(path: str):
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError as e:
                    raise DatasetError(f"{path}:{number}: not JSON ({e})") from None


def load(data_dir: str, split: str = "test") -> SciFactData:
    missing = [rel for rel in split_files(split) if not os.path.isfile(os.path.join(data_dir, rel))]
    if missing:
        raise DatasetError(f"{data_dir} lacks {', '.join(missing)}: run /retrieval load-scifact first")
    corpus = {}
    for row in _jsonl(os.path.join(data_dir, "corpus.jsonl")):
        corpus[str(row["_id"])] = {"title": row.get("title") or "", "text": row.get("text") or ""}
    all_queries = {str(row["_id"]): row.get("text") or "" for row in _jsonl(os.path.join(data_dir, "queries.jsonl"))}

    qrels: Dict[str, Dict[str, int]] = {}
    with open(os.path.join(data_dir, "qrels", f"{split}.tsv"), encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            cells = line.rstrip("\r\n").split("\t")
            if not line.strip() or (number == 1 and cells[0] == "query-id"):
                continue
            if len(cells) < 3:
                raise DatasetError(f"qrels/{split}.tsv:{number}: expected query-id, corpus-id, score")
            try:
                grade = int(float(cells[2]))
            except ValueError:
                raise DatasetError(f"qrels/{split}.tsv:{number}: score {cells[2]!r} is not a number") from None
            if grade > 0:
                qrels.setdefault(cells[0], {})[cells[1]] = grade

    unknown = sorted(q for q in qrels if q not in all_queries)
    if unknown:
        raise DatasetError(f"{len(unknown)} judged queries are missing from queries.jsonl (e.g. {unknown[0]})")
    source = {}
    source_path = os.path.join(data_dir, SOURCE_FILE)
    if os.path.isfile(source_path):
        with open(source_path, encoding="utf-8") as f:
            source = json.load(f)
    return SciFactData(corpus=corpus, queries={q: all_queries[q] for q in qrels}, qrels=qrels, split=split,
                       queries_in_file=len(all_queries), source=source, files=file_digests(data_dir, split))


def download(dest: str, split: str = "test", revision: str = REVISION, repo: str = REPO,
             url_template: str = "", timeout: float = 120.0) -> List[str]:
    """Fetch the split's files from the Hub into ``dest``; files already there are kept.

    Needs network access to huggingface.co (OSIRIS_HF_DATASET_URL names a mirror).
    Each file is written to a temporary name and renamed when complete.
    """
    url_template = url_template or os.environ.get("OSIRIS_HF_DATASET_URL") or DATASET_URL
    downloaded = []
    for rel in split_files(split):
        target = os.path.join(dest, rel)
        if os.path.isfile(target):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        url = url_template.format(repo=repo, revision=revision, path=rel)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".download-")
        try:
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=timeout) as resp:
                for chunk in iter(lambda: resp.read(1 << 20), b""):
                    out.write(chunk)
            os.replace(tmp, target)
        except (urllib.error.URLError, OSError) as e:
            if isinstance(e, urllib.error.HTTPError):
                e.close()
            if os.path.exists(tmp):
                os.remove(tmp)
            raise DatasetError(f"could not download {url}: {e}. This needs network access to huggingface.co; "
                               f"you can also copy {', '.join(split_files(split))} into {dest}") from e
        downloaded.append(rel)
    if downloaded:
        # Provenance for the files fetched here only; files that were already present
        # keep whatever SOURCE.json said about them (or nothing, if they were copied in).
        source_path = os.path.join(dest, SOURCE_FILE)
        source = {}
        if os.path.isfile(source_path):
            with open(source_path, encoding="utf-8") as f:
                source = json.load(f)
        files = dict(source.get("files", {}))
        files.update({rel: {"repo": repo, "revision": revision, "url": url_template.format(
            repo=repo, revision=revision, path=rel)} for rel in downloaded})
        with open(source_path, "w", encoding="utf-8") as f:
            json.dump({"files": files}, f, indent=2, sort_keys=True)
    return downloaded


def check_against_reference(data: SciFactData) -> List[str]:
    """Differences from the pinned mteb/scifact test split (sizes and counts; empty when it matches).

    The sizes come from the Hub listing of that revision; they and the counts catch a
    different or truncated copy, though not every edit.
    """
    problems = []
    if data.split != "test":
        problems.append(f"split is {data.split!r}, the reference is 'test'")
    for rel, size in EXPECTED_BYTES.items():
        got = data.files.get(rel, {}).get("bytes")
        if got != size:
            problems.append(f"{rel} is {got} bytes, the pinned revision's is {size}")
    pairs = sum(len(v) for v in data.qrels.values())
    for name, got, want in (("documents", len(data.corpus), EXPECTED_COUNTS["documents"]),
                            ("judged queries", len(data.queries), EXPECTED_COUNTS["queries"]),
                            ("relevant pairs", pairs, EXPECTED_COUNTS["relevant_pairs"])):
        if got != want:
            problems.append(f"{got} {name}, the reference has {want}")
    return problems
