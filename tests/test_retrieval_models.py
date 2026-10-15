"""The retrieval backend with a real (tiny, random-weight) Olmo3 sentence-transformer.

Skipped unless the optional extras are installed (pip install "osiris-cli[retrieval]").
The model is built locally with the same module layout as petegordon/olmo3-embed-7b --
an Olmo3Model, last-token pooling, L2 normalization -- but 32 dimensions and random
weights, so nothing is downloaded and the scores mean nothing. It checks that the
adapter loads such a model in bf16, passes the instruction on queries only, records
what it loaded, and drives the commands end to end.
"""
import json
import os
import sys

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
st = pytest.importorskip("sentence_transformers")
if not hasattr(transformers, "Olmo3Model"):
    pytest.skip("this transformers has no Olmo3 (needs 4.57+)", allow_module_level=True)

from sentence_transformers import SentenceTransformer  # noqa: E402

try:  # sentence-transformers 6 moved the modules; 5.x has them in .models
    from sentence_transformers.sentence_transformer.modules import Normalize, Pooling, Transformer
except ImportError:
    from sentence_transformers.models import Normalize, Pooling, Transformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_retrieval import CORPUS, QUERIES, write_dataset  # noqa: E402

from osiris_cli.retrieval import commands, policy  # noqa: E402
from osiris_cli.retrieval.embedder import EmbedderConfig, OlmoEmbedder  # noqa: E402
from osiris_cli.retrieval.evidence import verify_capsule  # noqa: E402


def build_tiny_olmo3_embedder(root):
    words = sorted({w for d in CORPUS.values() for w in (d["title"] + " " + d["text"]).lower().split()}
                   | {w for q in QUERIES.values() for w in q.lower().split()}
                   | {"instruct:", "query:", "given", "a", "scientific", "claim,", "retrieve"})
    base = os.path.join(root, "tiny-olmo3")
    os.makedirs(base)
    vocab = os.path.join(base, "vocab.txt")
    with open(vocab, "w", encoding="utf-8") as f:
        f.write("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"] + words) + "\n")
    tokenizer = transformers.BertTokenizerFast(vocab)
    torch.manual_seed(0)
    config = transformers.Olmo3Config(vocab_size=len(words) + 5, hidden_size=32, intermediate_size=64,
                                      num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=4,
                                      max_position_embeddings=1024, pad_token_id=0, eos_token_id=3)
    transformers.Olmo3Model(config).save_pretrained(base)
    tokenizer.save_pretrained(base)
    word = Transformer(base, max_seq_length=512)
    dimension = getattr(word, "get_embedding_dimension", None) or word.get_word_embedding_dimension
    pooling = Pooling(dimension(), pooling_mode="lasttoken")
    out = os.path.join(root, "tiny-olmo3-embed")
    SentenceTransformer(modules=[word, pooling, Normalize()], device="cpu").save(out)
    return out


@pytest.fixture(scope="module")
def model_dir(tmp_path_factory):
    return build_tiny_olmo3_embedder(str(tmp_path_factory.mktemp("models")))


def test_the_adapter_loads_in_bf16_and_prompts_queries_only(model_dir):
    emb = OlmoEmbedder(EmbedderConfig(model_id=model_dir, device="cpu", batch_size=2))
    q = emb.encode_queries(["vitamin d raises bone density"])
    d = emb.encode_documents(["vitamin d supplements raise bone density in adults", "cooking pasta"])
    assert q.shape == (1, 32) and d.shape == (2, 32) and str(q.dtype) == "float32"
    assert abs(float((q ** 2).sum()) - 1.0) < 1e-6                              # renormalized in float32
    env = emb.environment()
    assert (env["dtype"], env["embedding_dimension"], env["max_seq_length"]) == ("bfloat16", 32, 512)
    assert env["libraries"]["sentence_transformers"] == st.__version__
    plain = OlmoEmbedder(EmbedderConfig(model_id=model_dir, device="cpu", query_instruction=""))
    assert abs(plain.encode_queries(["vitamin d raises bone density"]) - q).max() > 1e-3   # instruction used
    assert abs(plain.encode_documents(["cooking pasta"]) - d[1:]).max() < 1e-6    # documents get none


def test_commands_end_to_end_with_a_real_model(model_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("OSIRIS_RETRIEVAL_HOME", str(tmp_path / "retrieval"))
    monkeypatch.setattr(policy, "is_edge", lambda env=None: False)
    write_dataset(tmp_path / "retrieval" / "scifact")
    common = f"--model {model_dir} --device cpu"
    assert "5 documents x 32 dims" in commands.run_command(f"build-index {common}")
    out = commands.run_command(f"run --full {common}")
    assert "3 of 3 queries" in out, out
    out = commands.run_command("evaluate")
    assert f"model {model_dir}" in out, out
    capsule = str(tmp_path / "tiny.evidence.zip")
    assert "self-check: intact" in commands.run_command(f"capsule {capsule}")
    assert verify_capsule(capsule)[0]
    run_dir = os.path.join(tmp_path, "retrieval", "runs", os.listdir(tmp_path / "retrieval" / "runs")[0])
    run = json.load(open(os.path.join(run_dir, "run.json")))
    assert run["environment"]["dtype"] == "bfloat16" and run["index"]["reused"] == 5   # built once, then cached
