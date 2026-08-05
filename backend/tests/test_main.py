import asyncio

import httpx
import pytest
from fastapi import HTTPException
import main


class LocalClient:
    def request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "PASSWORD_HASH_ITERATIONS", 1_000)
    main.init_database()
    yield LocalClient()


def register(client, email="leitor@example.com"):
    response = client.post(
        "/auth/register",
        json={"name": "Leitor", "email": email, "password": "senha-segura"},
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(data):
    return {"Authorization": f"Bearer {data['token']}"}


def test_health_check(client):
    assert client.get("/").json() == {"status": "ok"}


def test_register_login_and_me(client):
    registered = register(client)
    assert registered["user"]["email"] == "leitor@example.com"

    me = client.get("/auth/me", headers=auth_headers(registered))
    assert me.status_code == 200
    assert me.json()["name"] == "Leitor"

    login = client.post(
        "/auth/login", json={"email": "leitor@example.com", "password": "senha-segura"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == registered["user"]["id"]


def test_duplicate_email_and_wrong_password(client):
    register(client)
    duplicate = client.post(
        "/auth/register",
        json={"name": "Outro", "email": "LEITOR@example.com", "password": "outra-senha"},
    )
    assert duplicate.status_code == 409
    invalid = client.post(
        "/auth/login", json={"email": "leitor@example.com", "password": "senha-errada"}
    )
    assert invalid.status_code == 401


def test_conversation_is_saved_and_private(client, monkeypatch):
    first = register(client)
    second = register(client, "outro@example.com")

    async def fake_openrouter(_messages):
        return "Leia Torto Arado."

    monkeypatch.setattr(main, "call_openrouter", fake_openrouter)
    response = client.post(
        "/chat",
        json={"message": "O que devo ler?"},
        headers=auth_headers(first),
    )
    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]

    listing = client.get("/conversations", headers=auth_headers(first)).json()
    assert len(listing) == 1
    opened = client.get(
        f"/conversations/{conversation_id}", headers=auth_headers(first)
    ).json()
    assert [item["role"] for item in opened["messages"]] == ["user", "assistant"]
    assert client.get(
        f"/conversations/{conversation_id}", headers=auth_headers(second)
    ).status_code == 404


def test_delete_conversation(client, monkeypatch):
    auth = register(client)

    async def fake_openrouter(_messages):
        return "Resumo."

    monkeypatch.setattr(main, "call_openrouter", fake_openrouter)
    created = client.post(
        "/resumo", json={"titulo": "Duna"}, headers=auth_headers(auth)
    ).json()
    response = client.delete(
        f"/conversations/{created['conversation_id']}", headers=auth_headers(auth)
    )
    assert response.status_code == 204
    assert client.get("/conversations", headers=auth_headers(auth)).json() == []


def test_unauthenticated_history_is_rejected(client):
    assert client.get("/conversations").status_code == 401


def test_password_hash_is_salted(monkeypatch):
    monkeypatch.setattr(main, "PASSWORD_HASH_ITERATIONS", 1_000)
    first = main.hash_password("senha-segura")
    second = main.hash_password("senha-segura")
    assert first != second
    assert main.verify_password("senha-segura", first)
    assert not main.verify_password("incorreta", first)


def test_call_openrouter_missing_api_key(monkeypatch):
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", None)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.call_openrouter([{"role": "user", "content": "oi"}]))
    assert exc_info.value.status_code == 500


def test_call_openrouter_connection_error(monkeypatch):
    class BrokenClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, *_args, **_kwargs): raise httpx.RequestError("offline")

    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: BrokenClient())
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.call_openrouter([{"role": "user", "content": "oi"}]))
    assert exc_info.value.status_code == 502
