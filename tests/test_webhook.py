import importlib

import httpx
import pytest
from unittest.mock import AsyncMock


def _load_main(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return importlib.import_module("app.main")


def _text_payload():
    return {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {
                "remoteJid": "5541999999999@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"conversation": "gastei 45 no ifood"},
        },
    }


@pytest.mark.asyncio
async def test_webhook_processes_text_message_and_sends_response(monkeypatch):
    main = _load_main(monkeypatch)
    agent = AsyncMock()
    agent.process.return_value = "Gasto registrado"
    whatsapp = AsyncMock()
    whatsapp.send_text.return_value = True
    monkeypatch.setattr(main, "agent", agent)
    monkeypatch.setattr(main, "whatsapp", whatsapp)
    monkeypatch.setattr(main, "EVOLUTION_WEBHOOK_SECRET", "")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/webhook", json=_text_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    agent.process.assert_awaited_once_with(
        phone="5541999999999",
        message="gastei 45 no ifood",
    )
    whatsapp.send_text.assert_awaited_once_with(
        phone="5541999999999",
        message="Gasto registrado",
    )


@pytest.mark.asyncio
async def test_webhook_ignores_own_message(monkeypatch):
    main = _load_main(monkeypatch)
    agent = AsyncMock()
    whatsapp = AsyncMock()
    monkeypatch.setattr(main, "agent", agent)
    monkeypatch.setattr(main, "whatsapp", whatsapp)
    monkeypatch.setattr(main, "EVOLUTION_WEBHOOK_SECRET", "")

    payload = _text_payload()
    payload["data"]["key"]["fromMe"] = True

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/webhook", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "from_me"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_ignores_unsupported_event(monkeypatch):
    main = _load_main(monkeypatch)
    agent = AsyncMock()
    whatsapp = AsyncMock()
    monkeypatch.setattr(main, "agent", agent)
    monkeypatch.setattr(main, "whatsapp", whatsapp)
    monkeypatch.setattr(main, "EVOLUTION_WEBHOOK_SECRET", "")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/webhook", json={"event": "CONNECTION_UPDATE", "data": {}})

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "unsupported_event"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_secret(monkeypatch):
    main = _load_main(monkeypatch)
    agent = AsyncMock()
    whatsapp = AsyncMock()
    monkeypatch.setattr(main, "agent", agent)
    monkeypatch.setattr(main, "whatsapp", whatsapp)
    monkeypatch.setattr(main, "EVOLUTION_WEBHOOK_SECRET", "expected-secret")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/webhook?secret=wrong-secret", json=_text_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid webhook secret"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_accepts_valid_query_secret(monkeypatch):
    main = _load_main(monkeypatch)
    agent = AsyncMock()
    agent.process.return_value = "Gasto registrado"
    whatsapp = AsyncMock()
    whatsapp.send_text.return_value = True
    monkeypatch.setattr(main, "agent", agent)
    monkeypatch.setattr(main, "whatsapp", whatsapp)
    monkeypatch.setattr(main, "EVOLUTION_WEBHOOK_SECRET", "expected-secret")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/webhook?secret=expected-secret", json=_text_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    agent.process.assert_awaited_once()
    whatsapp.send_text.assert_awaited_once()
