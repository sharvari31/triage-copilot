# Demo kit

## Live URL checklist (run before every demo)
- [ ] Wake it up 2 min early: open https://triage-copilot-tbau.onrender.com/health → `status: ok`, `kb_chunks: 28`
- [ ] https://triage-copilot-tbau.onrender.com/docs loads
- [ ] Happy path: "Forgot password" ticket → `pending_approval`, cites `KB-006`, assignee `identity-team`
- [ ] Escalation path: off-topic ticket → `escalated` with a clear `escalation_reason`
- [ ] `/approve` works once, second call returns **409**
- [ ] Wrong `X-API-Key` → **401**
- [ ] GitHub repo is public and README shows eval results; **no `.env` in the repo**
- [ ] Groq key still valid (console.groq.com → API Keys)

## 60-second demo script

**0-10 s — Problem.** "Support agents spend most of their time sorting tickets and searching help articles.
This copilot does the first pass, and a human always approves before anything goes out."

**10-25 s — Happy path.** In `/docs`, run `POST /triage` with *"I can't log in and the reset email never
arrives."* Point at: category `account`, the retrieved article **KB-006** with its score, the draft that
**cites KB-006**, and assignee `identity-team`.

**25-40 s — Safety.** Run a ticket the KB can't answer, e.g. *"Can I pay my invoice in Bitcoin?"* →
`escalated: low_retrieval_confidence`. "It doesn't guess. Same for invalid LLM output, made-up citations, or a
failed self-check. On my very first real run, the checker caught the model inventing 'the link is sent
instantly', so I added one self-correction pass."

**40-50 s — Human in the loop.** `POST /approve` → approved; call it again → 409. "In production this
webhook posts the reply back into the Node/Express ticketing app."

**50-60 s — Engineering.** "LangGraph agent, Chroma RAG, Pydantic-validated JSON with retry and fallback model,
26 tests including timeouts and invalid JSON, a 40-ticket eval, Docker, live on Render, plus AWS ECS and Cloud
Run deploy scripts. The prompt log shows how I worked with Claude and what I fixed myself."
