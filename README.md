# Ticket Triage Copilot

A Python microservice for an existing Node/Express/MongoDB/React ticketing system. When a ticket arrives, a
LangGraph agent classifies it, retrieves knowledge-base articles (RAG), drafts a cited reply, self-checks the
draft and proposes an assignee. **Nothing is sent until a human calls `/approve`.**

_Full README (architecture, deploy, improvements) is finalized at the end of the build._

## Run locally
```powershell
copy .env.example .env      # then paste your GROQ_API_KEY into .env
docker compose up --build
```

## Evaluation
<!-- EVAL:START -->
Not run yet: `docker compose run --rm api python -m scripts.eval`
<!-- EVAL:END -->
