from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["billing", "account", "technical", "shipping", "returns", "general"]
Priority = Literal["low", "medium", "high", "urgent"]


class TicketIn(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)
    customer_email: str | None = None


# ---- LLM outputs (validated with Pydantic; invalid -> retry -> fallback -> escalate)
class Classification(BaseModel):
    category: Category
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=400)


class Draft(BaseModel):
    reply: str = Field(min_length=20, max_length=4000)
    citations: list[str] = Field(min_length=1, description="KB article ids used, e.g. KB-001")


class SelfCheck(BaseModel):
    grounded: bool = Field(description="Every factual claim is supported by the cited articles")
    answers_question: bool
    issues: list[str] = Field(default_factory=list)


# ---- API models
class ArticleHit(BaseModel):
    article_id: str
    title: str
    score: float
    text: str


class TriageResult(BaseModel):
    triage_id: str
    ticket_id: str
    status: Literal["pending_approval", "escalated"]
    classification: Classification | None = None
    articles: list[ArticleHit] = Field(default_factory=list)
    draft: Draft | None = None
    self_check: SelfCheck | None = None
    assignee: str
    assignee_reason: str
    escalation_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApproveIn(BaseModel):
    triage_id: str
    approved: bool
    reviewer: str = Field(min_length=1)
    edited_reply: str | None = Field(default=None, min_length=1)
    assignee: str | None = None


class ApproveOut(BaseModel):
    triage_id: str
    decision: Literal["approved", "rejected"]
    final_reply: str | None
    assignee: str
    delivery: str
