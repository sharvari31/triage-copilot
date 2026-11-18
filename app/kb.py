"""Knowledge base: markdown -> chunks -> ChromaDB (cosine) with a free local embedding model.

Chunking: articles are short (~80-150 words), so each article is ONE chunk (title + body).
One chunk == one citable article keeps citations exact and avoids splitting an answer
from its context. Only articles longer than MAX_WORDS are split at H2 ("## ") headings,
and every chunk keeps the article title so it still embeds with its topic.
"""
import asyncio
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from .schemas import ArticleHit

MAX_WORDS = 350


def parse_article(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("article missing front matter")
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    body = re.sub(r"^# .*\n", "", m.group(2).strip()).strip()
    return {"id": meta["id"], "title": meta["title"], "category": meta.get("category", "general"), "body": body}


def chunk_article(art: dict) -> list[dict]:
    if len(art["body"].split()) <= MAX_WORDS:
        sections = [art["body"]]
    else:
        sections = [s.strip() for s in re.split(r"\n(?=## )", art["body"]) if s.strip()]
    return [
        {
            "id": f"{art['id']}#{i}",
            "text": f"{art['title']}\n\n{sec}",
            "meta": {"article_id": art["id"], "title": art["title"], "category": art["category"]},
        }
        for i, sec in enumerate(sections)
    ]


class KnowledgeBase:
    def __init__(self, path: str, embedding_function=None, collection: str = "support_kb"):
        if embedding_function is None:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            embedding_function = DefaultEmbeddingFunction()  # all-MiniLM-L6-v2 (ONNX, CPU, free)
        self._client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self._col = self._client.get_or_create_collection(
            collection, embedding_function=embedding_function, metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self._col.count()

    def ingest(self, kb_dir: str) -> int:
        chunks = []
        for f in sorted(Path(kb_dir).glob("*.md")):
            chunks += chunk_article(parse_article(f.read_text(encoding="utf-8")))
        if chunks:
            self._col.upsert(
                ids=[c["id"] for c in chunks],
                documents=[c["text"] for c in chunks],
                metadatas=[c["meta"] for c in chunks],
            )
        return len(chunks)

    def search_sync(self, query: str, k: int = 3) -> list[ArticleHit]:
        n = min(max(k * 2, 1), max(self.count(), 1))
        res = self._col.query(query_texts=[query], n_results=n)
        best: dict[str, ArticleHit] = {}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            hit = ArticleHit(article_id=meta["article_id"], title=meta["title"], score=round(1 - dist, 4), text=doc)
            if hit.article_id not in best or hit.score > best[hit.article_id].score:
                best[hit.article_id] = hit
        return sorted(best.values(), key=lambda h: h.score, reverse=True)[:k]

    async def search(self, query: str, k: int = 3) -> list[ArticleHit]:
        return await asyncio.to_thread(self.search_sync, query, k)
