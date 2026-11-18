"""Evaluate classification accuracy + retrieval hit rate on eval/tickets.jsonl.

  python -m scripts.eval                   # retrieval + classification (needs GROQ_API_KEY)
  python -m scripts.eval --retrieval-only  # no LLM calls
Writes eval/results.md and replaces the EVAL block in README.md.
"""
import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from app.config import Settings
from app.graph import CLASSIFY_SYS
from app.kb import KnowledgeBase
from app.llm import LLMFailure, call_json, make_groq_models
from app.schemas import Classification


async def main(retrieval_only: bool):
    s = Settings()
    kb = KnowledgeBase(s.chroma_dir)
    models = [] if retrieval_only else make_groq_models(s.groq_api_key, s.primary_model, s.fallback_model, s.llm_timeout_s)
    if not retrieval_only and not models:
        raise SystemExit("GROQ_API_KEY not set (or use --retrieval-only)")
    rows = [json.loads(l) for l in Path("eval/tickets.jsonl").read_text().splitlines() if l.strip()]
    hit1 = hit3 = above = correct = llm_fail = 0
    confusion, misses = Counter(), []
    for r in rows:
        hits = kb.search_sync(f"{r['subject']}\n{r['body']}", 3)
        ids = [h.article_id for h in hits]
        hit1 += bool(ids) and ids[0] == r["article_id"]
        hit3 += r["article_id"] in ids
        above += bool(hits) and hits[0].score >= s.min_retrieval_score
        if r["article_id"] not in ids:
            misses.append(f"{r['ticket_id']} want {r['article_id']} got {ids}")
        if not retrieval_only:
            try:
                c = await call_json(models, CLASSIFY_SYS, f"Subject: {r['subject']}\n\n{r['body']}", Classification, s.llm_timeout_s)
                correct += c.category == r["category"]
                if c.category != r["category"]:
                    confusion[f"{r['category']} -> {c.category}"] += 1
            except LLMFailure:
                llm_fail += 1
            await asyncio.sleep(1.5)  # stay under Groq free-tier rate limits
    n = len(rows)
    lines = [
        f"Eval set: {n} labelled tickets, KB of 28 articles, top_k=3, threshold={s.min_retrieval_score}, model={s.primary_model}",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Retrieval hit@1 | {hit1}/{n} = {hit1/n:.0%} |",
        f"| Retrieval hit@3 | {hit3}/{n} = {hit3/n:.0%} |",
        f"| Top hit above threshold (would not escalate) | {above}/{n} = {above/n:.0%} |",
    ]
    if not retrieval_only:
        lines += [f"| Classification accuracy | {correct}/{n} = {correct/n:.0%} |",
                  f"| LLM failures (escalated) | {llm_fail}/{n} |"]
    lines += ["", "Retrieval misses (hit@3): " + ("; ".join(misses) or "none")]
    if confusion:
        lines += ["Classification errors: " + ", ".join(f"{k} x{v}" for k, v in confusion.items())]
    report = "\n".join(lines)
    print(report)
    Path("eval/results.md").write_text(report + "\n")
    readme = Path("README.md")
    if readme.exists():
        txt = re.sub(r"<!-- EVAL:START -->.*<!-- EVAL:END -->",
                     f"<!-- EVAL:START -->\n{report}\n<!-- EVAL:END -->", readme.read_text(), flags=re.S)
        readme.write_text(txt)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    asyncio.run(main(ap.parse_args().retrieval_only))
