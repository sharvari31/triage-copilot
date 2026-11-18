"""Build the Chroma index from kb/*.md.  Usage: python -m scripts.ingest"""
from app.config import Settings
from app.kb import KnowledgeBase

if __name__ == "__main__":
    s = Settings()
    kb = KnowledgeBase(s.chroma_dir)
    n = kb.ingest(s.kb_dir)
    print(f"ingested {n} chunks from {s.kb_dir} into {s.chroma_dir} (total {kb.count()})")
    print("smoke test:", [(h.article_id, h.score) for h in kb.search_sync("I forgot my password", 3)])
