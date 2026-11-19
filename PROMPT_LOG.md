# Prompt log: how I built this with Claude

Fill in **"What I changed / fixed myself"** as you go. That column shows the reviewer your own judgment.

| # | Time (IST) | My prompt (summary) | What Claude did | What I changed / fixed myself |
|---|---|---|---|---|
| 1 | 10:29 | "FAST MODE. Plan in <15 lines, deploy before extras, 1 test command + 3 failure modes per feature, PROMPT_LOG, README, demo script." | Asked what to build instead of guessing; proposed a default stack. | Gave the full project spec. |
| 2 | 10:30 | Full spec: FastAPI + LangGraph (classify → retrieve → draft → self-check → route), RAG on Chroma, Groq structured JSON, 40-ticket eval, 12+ tests, Docker, AWS deploy. | 15-line plan. Picked ECS Fargate over Lambda (Chroma + SQLite need disk, plus cold starts). | Approved the plan; created the Groq key; AWS signup step by step. |
| 3 | 10:34 | "go" | Checked Groq docs and found that `llama-3.3-70b-versatile` was shut down for free tier on 2026-08-16, so it uses `openai/gpt-oss-120b` with `gpt-oss-20b` as fallback. Built KB (28 articles), graph, API, 25 tests (fake LLM + fake embeddings), eval set, Docker. | _e.g. ran tests locally, built the image, tuned MIN_RETRIEVAL_SCORE after eval_ |
| 4 | 10:51 | Pasted Docker error: port 8000 already allocated. | Gave port-finding command + remap option. | Remapped host port to 8001. |
| 5 | 10:55 | Pasted 401 `invalid or missing X-API-Key`. | Explained that auth works and the placeholder was being sent; gave a command that reads the key from `.env`. | Set GROQ_API_KEY + SERVICE_API_KEY in `.env`. |
| 6 | 11:05 | Pasted first real triage: **escalated**. The LLM draft invented "reset link sent instantly" and the self-check caught it. | Added a self-correction loop (reviewer issues → one redraft → re-check → escalate if still bad). Escalations keep the rejected draft for the human. 26 tests. | Spotted that the guardrail worked but the happy path never completed. |
| 7 | 11:17 | "Start AWS from scratch on a new account with credits. Credits won't be used until someone tests it, right?" | Corrected me: Fargate bills per running second, not per request (~$0.75/day at 0.5 vCPU / 1 GB), and fixed its own earlier $10-12/mo estimate. Recommended the Free plan + stop/start scripts. | Created the new Free-plan account, budget alert, and `deployer` IAM user. Caught that the user had no permissions attached on the review screen and fixed it. |
| 8 | 12:36 | AWS CLI configured. | Wrote `deploy/deploy.ps1` (one idempotent command: Secrets Manager → ECR push → IAM exec role → logs → ECS cluster → task def → SG → service → prints live URL) plus `stop/start/url/teardown.ps1`. | |
| 9 | 12:44 | Ran `deploy.ps1`; pasted `AccessDenied ... explicit deny in a service control policy` on Secrets Manager. | Identified the AWS Free-plan SCP (not an IAM problem); gave 3 CLI probes. ECS, ECR and SSM were all denied too. | Ran the probes; decided to ship on **Render** now and keep the AWS scripts as the documented production path. |
| 10 | 12:46 | "Go Render." | Added `render.yaml` Blueprint, made the container honour `$PORT`, lowered memory use (single-thread ONNX) for Render's 512 MB free tier. | |
| 11 | | | | |

## Key decisions (and why)
- **Escalate, never guess:** low retrieval score, invalid LLM output after retry and fallback, a hallucinated citation, or a failed self-check all route to a human with the reason attached.
- **Assignee is rule-based, not LLM-based:** category plus priority maps to a team table, so it's deterministic and auditable.
- **Citations validated in code:** the draft may only cite article ids that were actually retrieved, otherwise it's retried and then escalated.
- **Embedding model baked into the Docker image:** no downloads at runtime, so startup is fast and reliable on ECS.
