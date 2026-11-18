"""LangGraph: classify -> retrieve -> draft -> self_check -> route, with escalate on any failure.

Rule: if we're unsure, we escalate to a human. We never guess.
"""
import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph

from .config import Settings
from .llm import LLMFailure, call_json
from .schemas import ArticleHit, Classification, Draft, SelfCheck, TicketIn, TriageResult

TEAMS = {
    "billing": "billing-team",
    "account": "identity-team",
    "technical": "tier2-tech-support",
    "shipping": "logistics-team",
    "returns": "returns-team",
    "general": "tier1-support",
}

CLASSIFY_SYS = """TASK: classify
You triage customer support tickets. Pick exactly one category:
- billing: payments, charges, invoices, subscriptions, plans
- account: login, password, 2FA, email change, lockout, account deletion
- technical: app/website bugs, crashes, sync, notifications, API, uploads
- shipping: tracking, delivery times, missing packages, address changes, customs
- returns: returns, refunds, damaged or wrong items
- general: support hours, privacy/data export, loyalty points, anything else
Priority: urgent = security risk, service fully down, or legal threat; high = customer blocked or money lost;
medium = degraded/annoying; low = question. confidence = your probability the category is correct."""

DRAFT_SYS = """TASK: draft
You write replies for a customer support agent to review. Use ONLY facts from the provided knowledge-base
articles. Do not invent policies, numbers, links or timelines. Be warm, concise (under 150 words) and give
concrete steps. Never add claims about timing, speed, availability or outcomes that the articles do not
state word-for-word in meaning. Cite every article you used by its id in `citations` (e.g. ["KB-006"]); you may also mention
it inline like [KB-006]. If the articles do not answer the question, say what you can and that a specialist
will follow up."""

CHECK_SYS = """TASK: review
You are a strict QA reviewer. Given the ticket, the articles and a draft reply, decide:
grounded = every factual claim in the draft is supported by the articles (no invented numbers or policies);
answers_question = the draft addresses the customer's actual problem. List concrete issues if any."""


class State(TypedDict, total=False):
    ticket: TicketIn
    classification: Classification
    hits: list[ArticleHit]
    draft: Draft
    self_check: SelfCheck
    escalation_reason: str
    feedback: str
    revisions: int
    result: TriageResult


def _ticket_text(t: TicketIn) -> str:
    return f"Subject: {t.subject}\n\n{t.body}"


def _articles_text(hits: list[ArticleHit]) -> str:
    return "\n\n".join(f"[{h.article_id}] {h.text}" for h in hits)


def build_graph(models, kb, settings: Settings):
    async def classify(state: State) -> State:
        try:
            c = await call_json(models, CLASSIFY_SYS, _ticket_text(state["ticket"]), Classification, settings.llm_timeout_s)
            return {"classification": c}
        except LLMFailure as e:
            return {"escalation_reason": f"classification_failed: {e}"}

    async def retrieve(state: State) -> State:
        t = state["ticket"]
        try:
            hits = await kb.search(f"{t.subject}\n{t.body}", settings.top_k)
        except Exception as e:  # vector store down / corrupt index
            return {"hits": [], "escalation_reason": f"retrieval_error: {type(e).__name__}: {e}"[:300]}
        good = [h for h in hits if h.score >= settings.min_retrieval_score]
        if not good:
            best = f"{hits[0].score:.2f}" if hits else "none"
            return {"hits": hits, "escalation_reason": f"low_retrieval_confidence (best score {best} < {settings.min_retrieval_score})"}
        return {"hits": good}

    async def draft(state: State) -> State:
        hits = state["hits"]
        allowed = {h.article_id for h in hits}

        def citations_must_exist(d: Draft):
            bad = [c for c in d.citations if c not in allowed]
            if bad:
                raise ValueError(f"citations {bad} are not in the provided articles {sorted(allowed)}")

        user = f"Ticket:\n{_ticket_text(state['ticket'])}\n\nKnowledge-base articles:\n{_articles_text(hits)}"
        if state.get("feedback"):
            user += (f"\n\nA QA reviewer REJECTED your previous draft:\n{state['draft'].reply}\n"
                     f"Issues: {state['feedback']}\nWrite a corrected draft that fixes every issue.")
        try:
            d = await call_json(models, DRAFT_SYS, user, Draft, settings.llm_timeout_s, extra_check=citations_must_exist)
            return {"draft": d, "feedback": ""}
        except LLMFailure as e:
            return {"escalation_reason": f"draft_failed: {e}"}

    async def self_check(state: State) -> State:
        d = state["draft"]
        user = (
            f"Ticket:\n{_ticket_text(state['ticket'])}\n\nArticles:\n{_articles_text(state['hits'])}"
            f"\n\nDraft reply:\n{d.reply}\n\nCited: {d.citations}"
        )
        try:
            sc = await call_json(models, CHECK_SYS, user, SelfCheck, settings.llm_timeout_s)
        except LLMFailure as e:
            return {"escalation_reason": f"self_check_failed: {e}"}
        if not (sc.grounded and sc.answers_question):
            issues = "; ".join(sc.issues) or "not grounded in the articles"
            if state.get("revisions", 0) < settings.max_revisions:  # one self-correction pass
                return {"self_check": sc, "feedback": issues, "revisions": state.get("revisions", 0) + 1}
            return {"self_check": sc, "escalation_reason": f"self_check_rejected: {'; '.join(sc.issues) or 'not grounded'}"}
        return {"self_check": sc}

    def _assignee(state: State) -> tuple[str, str]:
        c = state.get("classification")
        if not c:
            return "tier1-support", "no classification; default human triage queue"
        team = TEAMS[c.category]
        if c.priority == "urgent":
            return f"{team}-lead", f"{c.category} + urgent priority -> team lead"
        return team, f"category={c.category}, priority={c.priority}"

    def _result(state: State, status: str) -> TriageResult:
        assignee, why = _assignee(state)
        return TriageResult(
            triage_id=str(uuid.uuid4()),
            ticket_id=state["ticket"].ticket_id,
            status=status,
            classification=state.get("classification"),
            articles=state.get("hits", []),
            draft=state.get("draft"),  # on escalation: the rejected draft, for the human to edit
            self_check=state.get("self_check"),
            assignee=assignee,
            assignee_reason=why,
            escalation_reason=state.get("escalation_reason"),
        )

    async def route(state: State) -> State:
        return {"result": _result(state, "pending_approval")}

    async def escalate(state: State) -> State:
        return {"result": _result(state, "escalated")}

    def ok_or_escalate(next_node: str):
        return lambda s: "escalate" if s.get("escalation_reason") else next_node

    g = StateGraph(State)
    for name, fn in [("classify", classify), ("retrieve", retrieve), ("draft", draft),
                     ("self_check", self_check), ("route", route), ("escalate", escalate)]:
        g.add_node(name, fn)
    g.set_entry_point("classify")
    g.add_conditional_edges("classify", ok_or_escalate("retrieve"), ["retrieve", "escalate"])
    g.add_conditional_edges("retrieve", ok_or_escalate("draft"), ["draft", "escalate"])
    g.add_conditional_edges("draft", ok_or_escalate("self_check"), ["self_check", "escalate"])
    def after_check(s: State) -> str:
        if s.get("escalation_reason"):
            return "escalate"
        return "draft" if s.get("feedback") else "route"

    g.add_conditional_edges("self_check", after_check, ["draft", "route", "escalate"])
    g.add_edge("route", END)
    g.add_edge("escalate", END)
    return g.compile()


async def run_triage(graph, ticket: TicketIn) -> TriageResult:
    out = await graph.ainvoke({"ticket": ticket})
    return out["result"]
