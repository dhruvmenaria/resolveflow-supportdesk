import hashlib

import pytest

from resolveflow.db import get_session
from resolveflow.models import Translation
from resolveflow.main import app


@pytest.mark.asyncio
async def test_auth_required(client):
    response = await client.get("/tickets")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_support_draft_has_policy_citations_and_requires_review(client, auth_headers):
    created = await client.post("/tickets", headers=auth_headers, json={
        "customer_ref": "cust-1001",
        "message": "My order ORD-2048 arrived damaged. What can I do?",
    })
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    drafted = await client.post(f"/tickets/{ticket_id}/draft", headers=auth_headers)
    assert drafted.status_code == 200
    result = drafted.json()
    assert result["requires_human_review"] is True
    assert any(source["id"] == "returns-01" for source in result["sources"])
    assert result["order_context"]["found"] is True


@pytest.mark.asyncio
async def test_action_is_only_applied_after_approval(client, auth_headers):
    created = await client.post("/tickets", headers=auth_headers, json={
        "customer_ref": "cust-1001", "message": "The ceramic item broke, ORD-2048",
    })
    ticket_id = created.json()["id"]
    rejected = await client.post(f"/tickets/{ticket_id}/actions/approve", headers=auth_headers,
                                 json={"action": "replacement", "approved": False})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "open"
    approved = await client.post(f"/tickets/{ticket_id}/actions/approve", headers=auth_headers,
                                 json={"action": "replacement", "approved": True})
    assert approved.status_code == 200
    assert approved.json()["status"] == "replacement_approved"
    assert approved.json()["simulated"] is True


@pytest.mark.asyncio
async def test_translation_memory_hit_does_not_need_provider(client, auth_headers):
    text = "Your replacement is on the way."
    digest = hashlib.sha256(text.encode()).hexdigest()
    session_generator = app.dependency_overrides[get_session]()
    session = await anext(session_generator)
    try:
        session.add(Translation(user_id="demo", source_hash=digest, source_text=text,
                                translated_text="Su reemplazo está en camino.", source_locale="en", target_locale="es"))
        await session.commit()
    finally:
        await session_generator.aclose()
    response = await client.post("/translations/translate", headers=auth_headers, json={
        "source_text": text, "source_locale": "en", "target_locale": "es",
    })
    assert response.status_code == 200
    assert response.json()["cache_hit"] is True
    assert response.json()["source"] == "memory"


@pytest.mark.asyncio
async def test_translation_batch_limit_is_50(client, auth_headers):
    items = [{"source_text": f"line {i}", "source_locale": "en", "target_locale": "es"} for i in range(51)]
    response = await client.post("/translations/batch", headers=auth_headers, json={"items": items})
    assert response.status_code == 422
