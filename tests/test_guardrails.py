"""Failure modes: LLM timeout, invalid JSON, fallback model, empty/low retrieval, bad citations, self-check."""
import json

from app.llm import extract_json
from app.schemas import ArticleHit
from tests.conftest import GOOD, TICKET, FakeKB, FakeLLM


def triage(make_client, **kw):
    r = make_client(**kw).post("/triage", json=TICKET)
    assert r.status_code == 200, r.text
    return r.json()


def test_llm_timeout_escalates(make_client):
    body = triage(make_client, models=[FakeLLM({"classify": "SLEEP"})])
    assert body["status"] == "escalated"
    assert "timeout" in body["escalation_reason"]
    assert body["draft"] is None and body["assignee"] == "tier1-support"


def test_llm_exception_escalates(make_client):
    body = triage(make_client, models=[FakeLLM({"classify": RuntimeError("429 rate limited")})])
    assert body["status"] == "escalated" and "429" in body["escalation_reason"]


def test_invalid_json_then_valid_retries_and_succeeds(make_client):
    llm = FakeLLM({"classify": ["this is not json", GOOD["classify"]]})
    body = triage(make_client, models=[llm])
    assert body["status"] == "pending_approval"
    assert llm.calls.count("classify") == 2


def test_schema_violation_retried(make_client):
    bad = json.dumps({"category": "spaceships", "priority": "medium", "confidence": 2, "summary": "x"})
    llm = FakeLLM({"classify": [bad, GOOD["classify"]]})
    assert triage(make_client, models=[llm])["status"] == "pending_approval"


def test_invalid_json_always_escalates(make_client):
    body = triage(make_client, models=[FakeLLM({"classify": "{broken"})])
    assert body["status"] == "escalated" and "invalid output" in body["escalation_reason"]


def test_fallback_model_used_when_primary_times_out(make_client):
    primary, fallback = FakeLLM({"classify": "SLEEP"}), FakeLLM()
    body = triage(make_client, models=[primary, fallback])
    assert body["status"] == "pending_approval"
    assert "classify" in fallback.calls


def test_empty_retrieval_escalates_without_drafting(make_client):
    llm = FakeLLM()
    body = triage(make_client, models=[llm], kb=FakeKB(hits=[]))
    assert body["status"] == "escalated"
    assert "low_retrieval_confidence" in body["escalation_reason"]
    assert "draft" not in llm.calls  # never guess without sources
    assert body["assignee"] == "identity-team"  # still routed to the right humans


def test_low_score_retrieval_escalates(make_client):
    kb = FakeKB(hits=[ArticleHit(article_id="KB-028", title="Loyalty", score=0.12, text="points")])
    body = triage(make_client, kb=kb)
    assert body["status"] == "escalated" and "0.12" in body["escalation_reason"]


def test_hallucinated_citation_rejected(make_client):
    fake_cite = json.dumps({"reply": "Please contact our legal department today for help.", "citations": ["KB-999"]})
    body = triage(make_client, models=[FakeLLM({"draft": fake_cite})])
    assert body["status"] == "escalated" and "KB-999" in body["escalation_reason"]


REJECT = json.dumps({"grounded": False, "answers_question": True, "issues": ["invents a 7-day timeline"]})


def test_self_check_failure_revises_then_escalates(make_client):
    llm = FakeLLM({"review": REJECT})
    body = triage(make_client, models=[llm])
    assert body["status"] == "escalated"
    assert "invents a 7-day timeline" in body["escalation_reason"]
    assert llm.calls.count("draft") == 2  # one self-correction attempt, then give up
    assert body["draft"] is not None      # rejected draft kept for the human to edit


def test_self_check_revision_fixes_draft(make_client):
    llm = FakeLLM({"review": [REJECT, GOOD["review"]]})
    body = triage(make_client, models=[llm])
    assert body["status"] == "pending_approval" and llm.calls.count("draft") == 2


def test_urgent_routes_to_lead(make_client):
    urgent = json.dumps({"category": "account", "priority": "urgent", "confidence": 0.9, "summary": "hacked"})
    body = triage(make_client, models=[FakeLLM({"classify": urgent})])
    assert body["assignee"] == "identity-team-lead"


def test_no_llm_configured_escalates(make_client):
    assert "no LLM configured" in triage(make_client, models=[])["escalation_reason"]


def test_extract_json_strips_fences():
    assert json.loads(extract_json('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(extract_json('Sure! {"a": 2} hope that helps')) == {"a": 2}


def test_vector_store_error_escalates(make_client):
    class BrokenKB(FakeKB):
        async def search(self, query, k=3):
            raise ConnectionError("chroma unavailable")

    body = triage(make_client, kb=BrokenKB())
    assert body["status"] == "escalated" and "retrieval_error" in body["escalation_reason"]
