"""Core path: /health, /triage happy path, /approve flows, auth."""
from tests.conftest import TICKET, FakeLLM


def test_health(make_client):
    r = make_client().get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_triage_happy_path(make_client):
    r = make_client().post("/triage", json=TICKET)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending_approval"
    assert body["classification"]["category"] == "account"
    assert body["draft"]["citations"] == ["KB-006"]
    assert body["assignee"] == "identity-team"
    assert body["escalation_reason"] is None


def test_approve_sends_reply(make_client):
    sent = []
    c = make_client(sent=sent)
    tid = c.post("/triage", json=TICKET).json()["triage_id"]
    r = c.post("/approve", json={"triage_id": tid, "approved": True, "reviewer": "asha"})
    assert r.status_code == 200 and r.json()["decision"] == "approved"
    assert len(sent) == 1 and sent[0]["ticket_id"] == "T-1" and "Forgot password" in sent[0]["reply"]


def test_nothing_sent_without_approval_and_reject_sends_nothing(make_client):
    sent = []
    c = make_client(sent=sent)
    tid = c.post("/triage", json=TICKET).json()["triage_id"]
    assert sent == []  # triage alone never sends
    r = c.post("/approve", json={"triage_id": tid, "approved": False, "reviewer": "asha"})
    assert r.json()["decision"] == "rejected" and sent == []


def test_approve_twice_conflict(make_client):
    c = make_client()
    tid = c.post("/triage", json=TICKET).json()["triage_id"]
    assert c.post("/approve", json={"triage_id": tid, "approved": True, "reviewer": "a"}).status_code == 200
    assert c.post("/approve", json={"triage_id": tid, "approved": True, "reviewer": "b"}).status_code == 409


def test_approve_unknown_id(make_client):
    r = make_client().post("/approve", json={"triage_id": "nope", "approved": True, "reviewer": "a"})
    assert r.status_code == 404


def test_escalated_needs_human_reply_to_approve(make_client):
    c = make_client(models=[FakeLLM({"classify": "SLEEP"})])
    tid = c.post("/triage", json=TICKET).json()["triage_id"]
    assert c.post("/approve", json={"triage_id": tid, "approved": True, "reviewer": "a"}).status_code == 422
    r = c.post("/approve", json={"triage_id": tid, "approved": True, "reviewer": "a",
                                 "edited_reply": "Hi, a specialist fixed this for you."})
    assert r.status_code == 200


def test_api_key_required_when_configured(make_client):
    c = make_client(api_key="s3cret")
    assert c.post("/triage", json=TICKET).status_code == 401
    assert c.post("/triage", json=TICKET, headers={"X-API-Key": "s3cret"}).status_code == 200
    assert c.get("/health").status_code == 200  # health stays open for load balancers


def test_invalid_ticket_rejected(make_client):
    assert make_client().post("/triage", json={"ticket_id": "T", "subject": "", "body": "x"}).status_code == 422
