import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.config import Settings
from app.graph import build_graph
from app.main import create_app
from app.schemas import ArticleHit
from app.store import Store

GOOD = {
    "classify": json.dumps({"category": "account", "priority": "medium", "confidence": 0.93,
                            "summary": "Customer cannot log in, forgot password"}),
    "draft": json.dumps({"reply": "Sorry about that! Click 'Forgot password' on the login page; the link is valid "
                                  "for 30 minutes [KB-006].", "citations": ["KB-006"]}),
    "review": json.dumps({"grounded": True, "answers_question": True, "issues": []}),
}


class FakeLLM:
    """Scripted chat model. script[task] is a list of responses consumed in order (last one repeats).
    A response can be a str (content), an Exception (raised) or the string "SLEEP" (hangs -> timeout)."""

    def __init__(self, script: dict | None = None):
        self.script = {k: list(v) if isinstance(v, list) else [v] for k, v in {**GOOD, **(script or {})}.items()}
        self.calls: list[str] = []

    async def ainvoke(self, messages):
        task = next(k for k in self.script if f"TASK: {k}" in messages[0].content)
        self.calls.append(task)
        queue = self.script[task]
        resp = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(resp, Exception):
            raise resp
        if resp == "SLEEP":
            await asyncio.sleep(10)
        return AIMessage(resp)


class FakeKB:
    def __init__(self, hits=None):
        self.hits = hits if hits is not None else [
            ArticleHit(article_id="KB-006", title="Reset your password", score=0.71,
                       text="Reset your password\n\nClick Forgot password... valid for 30 minutes."),
            ArticleHit(article_id="KB-009", title="Account locked", score=0.52, text="Account locked ..."),
        ]

    async def search(self, query, k=3):
        return self.hits[:k]

    def count(self):
        return len(self.hits)


TICKET = {"ticket_id": "T-1", "subject": "Can't log in", "body": "I forgot my password and can't get into my account."}


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.llm_timeout_s = 0.2
    s.min_retrieval_score = 0.35
    s.service_api_key = ""
    s.db_path = str(tmp_path / "t.db")
    return s


@pytest.fixture
def make_client(settings):
    def _make(models=None, kb=None, sent=None, api_key=""):
        settings.service_api_key = api_key
        models = models if models is not None else [FakeLLM()]
        kb = kb or FakeKB()
        sent = sent if sent is not None else []

        async def sender(payload):
            sent.append(payload)
            return "sent: fake"

        app = create_app(settings, graph=build_graph(models, kb, settings), kb=kb,
                         store=Store(settings.db_path), sender=sender)
        return TestClient(app)

    return _make
