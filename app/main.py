import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .config import Settings
from .graph import build_graph, run_triage
from .schemas import ApproveIn, ApproveOut, TicketIn, TriageResult
from .store import AlreadyDecided, Store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("triage")


def make_webhook_sender(url: str):
    async def send(payload: dict) -> str:
        if not url:
            return "not_sent: TICKETING_WEBHOOK_URL not configured"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
            return f"sent: webhook {r.status_code}"
        except httpx.HTTPError as e:
            log.error("webhook failed: %s", e)
            return f"failed: {type(e).__name__}"

    return send


def create_app(settings: Settings | None = None, graph=None, kb=None, store=None, sender=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.graph is None:
            from .kb import KnowledgeBase
            from .llm import make_groq_models

            app.state.kb = KnowledgeBase(settings.chroma_dir)
            models = make_groq_models(settings.groq_api_key, settings.primary_model,
                                      settings.fallback_model, settings.llm_timeout_s)
            if not models:
                log.warning("GROQ_API_KEY not set: every ticket will be escalated")
            app.state.graph = build_graph(models, app.state.kb, settings)
        if app.state.store is None:
            app.state.store = Store(settings.db_path)
        yield

    app = FastAPI(title="Ticket Triage Copilot", version="1.0.0", lifespan=lifespan)
    app.state.settings, app.state.graph, app.state.kb = settings, graph, kb
    app.state.store = store
    app.state.sender = sender or make_webhook_sender(settings.ticketing_webhook_url)

    def require_key(x_api_key: str | None = Header(default=None)):
        if settings.service_api_key and not hmac.compare_digest((x_api_key or "").strip(), settings.service_api_key):
            raise HTTPException(401, "invalid or missing X-API-Key")

    @app.get("/health")
    async def health(request: Request):
        kb = request.app.state.kb
        return {"status": "ok", "kb_chunks": kb.count() if kb else None, "model": settings.primary_model}

    @app.post("/triage", response_model=TriageResult, dependencies=[Depends(require_key)])
    async def triage(ticket: TicketIn, request: Request):
        result = await run_triage(request.app.state.graph, ticket)
        await request.app.state.store.save(result)
        log.info("triaged %s -> %s (%s)", ticket.ticket_id, result.status, result.escalation_reason or "ok")
        return result

    @app.post("/approve", response_model=ApproveOut, dependencies=[Depends(require_key)])
    async def approve(body: ApproveIn, request: Request):
        store: Store = request.app.state.store
        r = await store.get(body.triage_id)
        if r is None:
            raise HTTPException(404, "unknown triage_id")
        assignee = body.assignee or r.assignee
        if not body.approved:
            final_reply, decision = None, "rejected"
        else:
            if r.status == "escalated" and not body.edited_reply:
                raise HTTPException(422, "escalated ticket: a human must provide edited_reply to approve")
            final_reply = body.edited_reply or r.draft.reply
            decision = "approved"
        try:
            await store.decide(body.triage_id, decision, body.reviewer, final_reply, assignee)
        except AlreadyDecided:
            raise HTTPException(409, "triage already approved or rejected")
        delivery = "not_sent: rejected"
        if decision == "approved":
            delivery = await request.app.state.sender({
                "ticket_id": r.ticket_id, "triage_id": r.triage_id, "reply": final_reply,
                "assignee": assignee, "reviewer": body.reviewer,
                "citations": r.draft.citations if r.draft and not body.edited_reply else [],
            })
        return ApproveOut(triage_id=r.triage_id, decision=decision, final_reply=final_reply,
                          assignee=assignee, delivery=delivery)

    return app


app = create_app()
