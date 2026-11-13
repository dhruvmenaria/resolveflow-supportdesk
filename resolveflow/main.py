import hashlib
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import jwt
from fastapi import Depends, FastAPI, Form, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from .config import settings
from .db import Base, engine, get_session
from .knowledge import POLICIES, retrieve
from .llm import complete
from .models import AuditEvent, Draft, GlossaryTerm, Ticket, Translation, UsageEvent
from .schemas import ActionDecision, BatchTranslateRequest, GlossaryRequest, TicketCreate, TranslateRequest
from .security import current_user, make_token
from .tools import lookup_order


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="ResolveFlow", version="0.1.0", description="Grounded multilingual support workflows with human approval", lifespan=lifespan)


def ticket_json(ticket: Ticket) -> dict:
    return {"id": ticket.id, "customer_ref": ticket.customer_ref, "message": ticket.message,
            "status": ticket.status, "created_at": ticket.created_at}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "resolveflow"}


@app.post("/auth/token")
async def issue_token(username: str = Form(...), password: str = Form(...)):
    if username != settings.demo_username or password != settings.demo_password:
        raise HTTPException(status_code=401, detail="Incorrect demo credentials")
    return {"access_token": make_token(username), "token_type": "bearer", "expires_in_minutes": settings.jwt_expire_minutes}


@app.get("/knowledge")
async def list_knowledge(_: str = Depends(current_user)):
    return [{"id": d["id"], "title": d["title"], "text": d["text"]} for d in POLICIES]


@app.post("/tickets", status_code=201)
async def create_ticket(payload: TicketCreate, user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    ticket = Ticket(customer_ref=payload.customer_ref, message=payload.message)
    db.add(ticket)
    await db.flush()
    db.add(AuditEvent(user_id=user, event_type="ticket.created", entity_ref=str(ticket.id), detail=json.dumps({"customer_ref": payload.customer_ref})))
    await db.commit()
    await db.refresh(ticket)
    return ticket_json(ticket)


@app.get("/tickets")
async def list_tickets(_: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    rows = (await db.scalars(select(Ticket).order_by(Ticket.id.desc()))).all()
    return [ticket_json(row) for row in rows]


@app.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, _: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    draft = await db.scalar(select(Draft).where(Draft.ticket_id == ticket_id).order_by(Draft.id.desc()))
    return {**ticket_json(ticket), "latest_draft": None if draft is None else {
        "body": draft.body, "sources": json.loads(draft.sources), "order_context": json.loads(draft.order_context),
        "escalated": draft.escalated}}


@app.post("/tickets/{ticket_id}/draft")
async def create_draft(ticket_id: int, user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    sources = retrieve(ticket.message)
    order = lookup_order(ticket.message, ticket.customer_ref)
    sensitive = any(word in ticket.message.lower() for word in ("password", "credit card", "identity", "delete my data", "charged twice"))
    escalated = sensitive or not sources or sources[0]["score"] < 0.12
    if escalated:
        body = "This request needs a support specialist to review it. I have routed it to the human support queue."
    elif settings.llm_api_key:
        evidence = "\n".join(f"[{s['id']}] {s['text']}" for s in sources)
        order_text = json.dumps(order) if order else "No order record was found in the message. Do not infer order facts."
        try:
            body = await complete(
                "You draft concise customer-support replies. Use only the policy evidence and order facts supplied. "
                "Do not invent eligibility, dates, or actions. Do not claim any record-changing action has happened. "
                "If evidence is insufficient, say a human needs to review. Do not output citations; the API attaches them.",
                f"Customer message: {ticket.message}\nPolicy evidence:\n{evidence}\nOrder facts: {order_text}",
            )
            db.add(UsageEvent(user_id=user, event_type="llm.support_draft"))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM provider request failed: {type(exc).__name__}") from exc
    else:
        body = "Thanks for letting us know. " + sources[0]["text"] + " A support agent will review the details before any replacement or refund is confirmed."
    draft = Draft(ticket_id=ticket.id, body=body, sources=json.dumps([{"id": s["id"], "title": s["title"], "score": s["score"]} for s in sources]), order_context=json.dumps(order or {}), escalated=escalated)
    db.add(draft)
    db.add(UsageEvent(user_id=user, event_type="support.draft"))
    db.add(AuditEvent(user_id=user, event_type="draft.created", entity_ref=str(ticket.id), detail=json.dumps({"source_ids": [s["id"] for s in sources], "escalated": escalated})))
    await db.commit()
    await db.refresh(draft)
    return {"draft_id": draft.id, "ticket_id": ticket.id, "body": body,
            "sources": json.loads(draft.sources), "order_context": order,
            "escalated": escalated, "requires_human_review": True,
            "mode": "llm" if settings.llm_api_key and not escalated else "grounded_template"}


@app.post("/tickets/{ticket_id}/actions/approve")
async def decide_action(ticket_id: int, decision: ActionDecision, user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if decision.approved:
        if decision.action == "replacement":
            order = lookup_order(ticket.message, ticket.customer_ref)
            if not order or not order.get("found"):
                raise HTTPException(status_code=409, detail="Cannot approve replacement without a matching demo order")
            ticket.status = "replacement_approved"
        elif decision.action == "close_ticket":
            ticket.status = "closed"
    db.add(AuditEvent(user_id=user, event_type=f"action.{decision.action}.{ 'approved' if decision.approved else 'rejected'}",
                      entity_ref=str(ticket.id), detail=json.dumps({"reviewer_note": decision.reviewer_note})))
    db.add(UsageEvent(user_id=user, event_type="action.approval" if decision.approved else "action.rejection"))
    await db.commit()
    return {"ticket_id": ticket.id, "status": ticket.status, "action": decision.action,
            "decision": "approved" if decision.approved else "rejected", "simulated": True}


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


async def translate_one(payload: TranslateRequest, user: str, db: AsyncSession) -> dict:
    digest = text_hash(payload.source_text)
    cached = await db.scalar(select(Translation).where(
        Translation.user_id == user, Translation.source_hash == digest,
        Translation.source_locale == payload.source_locale, Translation.target_locale == payload.target_locale))
    if cached:
        db.add(UsageEvent(user_id=user, event_type="translation.cache_hit"))
        return {"source_text": payload.source_text, "translated_text": cached.translated_text, "source": "memory", "cache_hit": True}
    if not settings.llm_api_key:
        raise HTTPException(status_code=503, detail="Translation memory miss and no LLM provider is configured")
    glossary = (await db.scalars(select(GlossaryTerm).where(
        GlossaryTerm.user_id == user, GlossaryTerm.source_locale == payload.source_locale,
        GlossaryTerm.target_locale == payload.target_locale))).all()
    glossary_text = "\n".join(f"{term.source_term} => {term.target_term}" for term in glossary) or "No glossary terms."
    try:
        translated = await complete(
            "Translate faithfully. Return only translated text. Preserve placeholders, URLs, numbers and formatting. "
            "Apply glossary mappings exactly where the source term appears.",
            f"Translate from {payload.source_locale} to {payload.target_locale}. Glossary:\n{glossary_text}\nText:\n{payload.source_text}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Translation provider request failed: {type(exc).__name__}") from exc
    for term in glossary:
        if term.target_term not in translated and term.source_term.lower() in translated.lower():
            translated = re.sub(re.escape(term.source_term), term.target_term, translated, flags=re.IGNORECASE)
    db.add(Translation(user_id=user, source_hash=digest, source_text=payload.source_text,
                       translated_text=translated, source_locale=payload.source_locale, target_locale=payload.target_locale))
    db.add(UsageEvent(user_id=user, event_type="translation.llm_call"))
    db.add(AuditEvent(user_id=user, event_type="translation.created", entity_ref=digest[:16], detail=json.dumps({"source_locale": payload.source_locale, "target_locale": payload.target_locale})))
    return {"source_text": payload.source_text, "translated_text": translated, "source": "llm", "cache_hit": False}


@app.post("/translations/translate")
async def translate(payload: TranslateRequest, user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    result = await translate_one(payload, user, db)
    await db.commit()
    return result


@app.post("/translations/batch")
async def translate_batch(payload: BatchTranslateRequest, user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    results = []
    for item in payload.items:
        results.append(await translate_one(item, user, db))
    await db.commit()
    return {"count": len(results), "results": results}


@app.put("/glossary", status_code=201)
async def upsert_glossary(payload: GlossaryRequest, user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    term = await db.scalar(select(GlossaryTerm).where(
        GlossaryTerm.user_id == user, GlossaryTerm.source_term == payload.source_term,
        GlossaryTerm.source_locale == payload.source_locale, GlossaryTerm.target_locale == payload.target_locale))
    if term is None:
        term = GlossaryTerm(user_id=user, **payload.model_dump())
        db.add(term)
    else:
        term.target_term = payload.target_term
    await db.commit()
    return {"source_term": term.source_term, "target_term": term.target_term,
            "source_locale": term.source_locale, "target_locale": term.target_locale}


@app.get("/metrics")
async def metrics(user: str = Depends(current_user), db: AsyncSession = Depends(get_session)):
    async def count(model, *conditions):
        return int((await db.scalar(select(func.count()).select_from(model).where(*conditions))) or 0)
    return {
        "tickets": await count(Ticket),
        "drafts": await count(Draft),
        "translation_cache_hits": await count(UsageEvent, UsageEvent.user_id == user, UsageEvent.event_type == "translation.cache_hit"),
        "llm_calls": await count(UsageEvent, UsageEvent.user_id == user, UsageEvent.event_type.in_(["translation.llm_call", "llm.support_draft"])),
        "approval_decisions": await count(UsageEvent, UsageEvent.user_id == user, UsageEvent.event_type.in_(["action.approval", "action.rejection"])),
    }
