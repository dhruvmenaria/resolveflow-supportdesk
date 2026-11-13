import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from resolveflow.config import settings
from resolveflow.db import Base, get_session
from resolveflow.main import app


@pytest_asyncio.fixture
async def client(tmp_path):
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    old_secret, old_user, old_password = settings.jwt_secret, settings.demo_username, settings.demo_password
    settings.jwt_secret, settings.demo_username, settings.demo_password = "test-secret-with-at-least-32-characters", "demo", "test-pass"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    settings.jwt_secret, settings.demo_username, settings.demo_password = old_secret, old_user, old_password
    await test_engine.dispose()


@pytest_asyncio.fixture
async def auth_headers(client):
    response = await client.post("/auth/token", data={"username": "demo", "password": "test-pass"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
