# ResolveFlow

ResolveFlow is a portfolio demo for multilingual e-commerce support teams. It combines grounded ticket drafting, order lookup, an approval queue for actions, and translation memory so repeated support phrases do not need another model call.

## What it demonstrates

- Retrieve relevant policy passages and attach source IDs to every grounded draft.
- Look up demo order data through a typed tool; never let the model invent order status.
- Escalate when policy evidence is weak or an issue is sensitive.
- Require an authenticated human approval before a simulated record-changing action runs.
- Reuse exact translations, apply a per-user glossary, and accept batches of at most 50 strings.
- Record audit events and basic usage counters.
- Async FastAPI + SQLAlchemy 2, SQLite for a quick local run, PostgreSQL in Docker Compose.

All customers, orders, tickets, and policies are fictional demo data. No external email, refund, or customer action is performed.

## Quick start (Windows PowerShell)

```powershell
cd work/resolveflow
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn resolveflow.main:app --reload
```

Open <http://127.0.0.1:8000/docs>. Demo login defaults are `demo` / `change-this-password`; change them in `.env` before use beyond a local demo.

Run the automated checks with `python -m pytest -q`.

### PostgreSQL with Docker

```powershell
docker compose up --build
```

The API listens on port 8000. The compose file starts a local PostgreSQL database; it does not publish or connect to any external service.

## Try the API

1. `POST /auth/token` with form fields `username=demo`, `password=change-this-password`.
2. Authorize with the returned bearer token.
3. `POST /tickets` with `{"customer_ref":"cust-1001","message":"My order ORD-2048 arrived damaged. What can I do?"}`.
4. `POST /tickets/{ticket_id}/draft` to retrieve policy evidence, inspect the demo order, and create a cited draft.
5. Review the draft, then `POST /tickets/{ticket_id}/actions/approve` with `{"action":"replacement","approved":true}`. The action only updates the demo ticket/order record and is audited.
6. `POST /translations/translate` with `{"source_text":"Your replacement is on the way.","source_locale":"en","target_locale":"es"}`. A cache miss uses the configured LLM provider; without a provider key it returns a clear configuration error rather than pretending to translate.

Set `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` in `.env` to use an OpenAI-compatible chat-completions endpoint. Support drafting falls back to a clearly labeled evidence-based template when no provider is configured. Translation cache hits work without a provider.

## API overview

- `POST /auth/token` — issue a short-lived JWT for the configured demo account.
- `GET /health` — readiness check.
- `GET /knowledge` — list the fictional policy sources.
- `POST /tickets`, `GET /tickets`, `GET /tickets/{id}` — ticket lifecycle.
- `POST /tickets/{id}/draft` — retrieval, demo-order tool call, cited draft and escalation decision.
- `POST /tickets/{id}/actions/approve` — approve/reject a simulated action; approvals are recorded.
- `POST /translations/translate` — exact translation-memory lookup, glossary-aware provider call, and cache write.
- `POST /translations/batch` — translate 1–50 strings.
- `PUT /glossary` — add/update a term for the authenticated demo account.
- `GET /metrics` — basic counts for tickets, drafts, cache hits, model calls, and approvals.

## Safety and known limits

Retrieval uses a small transparent lexical scorer, suitable for explaining and testing the flow but not a substitute for a benchmarked production search stack. The demo LLM is instructed to use only retrieved evidence; the backend separately controls order facts, escalation, and approvals. This is a learning project, not a production support system: it has one demo tenant, no PII controls, no real payment integration, and no production-grade throttling or key rotation.

## Open-source references that informed the feature choices

This project was written from scratch. These repositories/docs are references for patterns, not source code copied into ResolveFlow:

- [ticket-triage-agent](https://github.com/jyothir-369/ticket-triage-agent) — retrieval, citations, escalation and audit trail.
- [HelpPilot](https://github.com/poysa213/HelpPilot) — human review before support actions.
- [Localization OS](https://github.com/patois-labs/localization-os) — translation memory, glossary and human review workflows.
- [LangChain human-in-the-loop docs](https://github.com/langchain-ai/docs/blob/main/src/oss/human-in-the-loop.mdx) — gating side-effecting tool calls.

## License

MIT. See [LICENSE](LICENSE).
