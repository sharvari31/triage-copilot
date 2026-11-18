"""Chunking + real ChromaDB ingest/search (with a tiny deterministic embedding so tests run offline)."""
import hashlib
import re

from chromadb import Documents, EmbeddingFunction, Embeddings

from app.kb import KnowledgeBase, chunk_article, parse_article


class BagOfWordsEF(EmbeddingFunction):
    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        out = []
        for doc in input:
            v = [0.0] * 256
            for w in re.findall(r"[a-z]+", doc.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1.0
            out.append(v)
        return out

    @staticmethod
    def name() -> str:
        return "bow-test"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return BagOfWordsEF()


def test_short_article_is_one_chunk_long_article_splits_on_h2():
    short = parse_article("---\nid: KB-1\ntitle: T\ncategory: billing\n---\n# T\n\nshort body")
    assert len(chunk_article(short)) == 1
    long_body = "\n".join(f"## Part {i}\n" + "word " * 200 for i in range(3))
    long = {"id": "KB-2", "title": "Long", "category": "general", "body": long_body}
    chunks = chunk_article(long)
    assert len(chunks) == 3 and all(c["text"].startswith("Long") for c in chunks)
    assert {c["meta"]["article_id"] for c in chunks} == {"KB-2"}


def test_ingest_real_kb_and_search(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "chroma"), embedding_function=BagOfWordsEF())
    assert kb.ingest("kb") == 28
    hits = kb.search_sync("forgot password reset link login", 3)
    assert hits[0].article_id == "KB-006"
    assert len({h.article_id for h in hits}) == len(hits)  # de-duplicated per article
