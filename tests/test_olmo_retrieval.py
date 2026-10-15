"""petegordon/olmo3-embed-7b itself: 4096-dimensional embeddings and a sensible ranking.

These download 13.8 GB of weights and need about 16 GB of memory, so they run only on
request: OSIRIS_TEST_OLMO3_EMBED=1 pytest tests/test_olmo_retrieval.py
(OSIRIS_TEST_OLMO3_REVISION pins a commit). CI and default runs skip them.
"""
import importlib.util
import os
import unittest

WANTED = os.environ.get("OSIRIS_TEST_OLMO3_EMBED") == "1"
HAVE_EXTRAS = all(importlib.util.find_spec(m) for m in ("torch", "sentence_transformers"))


@unittest.skipUnless(WANTED and HAVE_EXTRAS, "set OSIRIS_TEST_OLMO3_EMBED=1 with the [retrieval] extras installed")
class RealOlmo3EmbedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from osiris_cli.retrieval.embedder import EmbedderConfig, OlmoEmbedder

        cls.embedder = OlmoEmbedder(EmbedderConfig(revision=os.environ.get("OSIRIS_TEST_OLMO3_REVISION"),
                                                   batch_size=1))

    def test_query_and_document_embeddings_are_4096_dimensional_unit_vectors(self):
        query = self.embedder.encode_queries(["quantum error correction"])
        document = self.embedder.encode_documents(["Quantum error correction protects information."])
        self.assertEqual(query.shape, (1, 4096))
        self.assertEqual(document.shape, (1, 4096))
        self.assertAlmostEqual(float((query ** 2).sum()), 1.0, places=5)
        env = self.embedder.environment()
        self.assertEqual((env["embedding_dimension"], env["max_seq_length"], env["dtype"]), (4096, 512, "bfloat16"))
        self.assertIsNotNone(env["resolved_revision"])

    def test_retrieval_puts_the_on_topic_abstracts_first(self):
        from osiris_cli.retrieval.retrieval_loop import RetrievalLoop

        docs = {"d1": {"title": "A", "text": "quantum error correction"},
                "d2": {"title": "B", "text": "cooking pasta"},
                "d3": {"title": "C", "text": "quantum computing error rates"}}
        loop = RetrievalLoop(self.embedder, top_k=2)
        loop.build_index(docs)
        result = loop.retrieve("q1", "quantum error correction")
        self.assertEqual(len(result.ranked_doc_ids), 2)
        self.assertEqual(set(result.ranked_doc_ids), {"d1", "d3"})


if __name__ == "__main__":
    unittest.main()
