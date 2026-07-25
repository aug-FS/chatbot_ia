import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self._response


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_success(monkeypatch):
    async def fake_call_openrouter(messages):
        return "Resposta de teste"

    monkeypatch.setattr(main, "call_openrouter", fake_call_openrouter)

    response = client.post("/chat", json={"message": "oi"})

    assert response.status_code == 200
    assert response.json() == {"reply": "Resposta de teste"}


def test_chat_builds_messages_with_system_prompt_and_history(monkeypatch):
    captured = {}

    async def fake_call_openrouter(messages):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(main, "call_openrouter", fake_call_openrouter)

    response = client.post(
        "/chat",
        json={
            "message": "e ai?",
            "history": [
                {"role": "user", "content": "oi"},
                {"role": "assistant", "content": "ola"},
            ],
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    n_few_shot = len(main.FEW_SHOT_EXAMPLES)
    assert len(messages) == 1 + n_few_shot + 3
    assert messages[0] == {"role": "system", "content": main.SYSTEM_PROMPT}
    assert messages[1 : 1 + n_few_shot] == main.FEW_SHOT_EXAMPLES
    assert messages[1 + n_few_shot] == {"role": "user", "content": "oi"}
    assert messages[2 + n_few_shot] == {"role": "assistant", "content": "ola"}
    assert messages[3 + n_few_shot] == {"role": "user", "content": "e ai?"}


def test_chat_missing_message_returns_422():
    response = client.post("/chat", json={})
    assert response.status_code == 422


def test_resumo_success(monkeypatch):
    async def fake_call_openrouter(messages):
        return "Resumo de teste"

    monkeypatch.setattr(main, "call_openrouter", fake_call_openrouter)

    response = client.post("/resumo", json={"titulo": "Duna", "autor": "Frank Herbert"})

    assert response.status_code == 200
    assert response.json() == {"resumo": "Resumo de teste"}


def test_resumo_sem_autor_e_opcional(monkeypatch):
    async def fake_call_openrouter(messages):
        return "Resumo de teste"

    monkeypatch.setattr(main, "call_openrouter", fake_call_openrouter)

    response = client.post("/resumo", json={"titulo": "Duna"})

    assert response.status_code == 200


def test_resumo_missing_titulo_returns_422():
    response = client.post("/resumo", json={})
    assert response.status_code == 422


def test_call_openrouter_missing_api_key(monkeypatch):
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.call_openrouter([{"role": "user", "content": "oi"}]))

    assert exc_info.value.status_code == 500


def test_call_openrouter_upstream_error(monkeypatch):
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "fake-key")
    fake_response = FakeResponse(404, text='{"error": "model not found"}')
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **kw: FakeAsyncClient(fake_response))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.call_openrouter([{"role": "user", "content": "oi"}]))

    assert exc_info.value.status_code == 502


def test_call_openrouter_success_parses_reply(monkeypatch):
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "fake-key")
    fake_response = FakeResponse(
        200, json_data={"choices": [{"message": {"content": "Ola!"}}]}
    )
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **kw: FakeAsyncClient(fake_response))

    result = asyncio.run(main.call_openrouter([{"role": "user", "content": "oi"}]))

    assert result == "Ola!"
