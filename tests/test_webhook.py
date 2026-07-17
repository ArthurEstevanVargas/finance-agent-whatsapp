import importlib

import httpx
import pytest
from unittest.mock import AsyncMock


GROUP_JID = "120363012345678901@g.us"
OTHER_GROUP_JID = "120363099999999999@g.us"
PARTICIPANT_A = "5541999999999@s.whatsapp.net"
PARTICIPANT_B = "5541888888888@s.whatsapp.net"


def _load_main(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return importlib.import_module("app.main")


def _private_text_payload():
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


def _group_text_payload(group_jid=GROUP_JID, participant=PARTICIPANT_A, text="gastei 45 no ifood"):
    return {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {
                "remoteJid": group_jid,
                "participant": participant,
                "fromMe": False,
            },
            "message": {"conversation": text},
        },
    }


def _group_image_payload():
    return {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {
                "remoteJid": GROUP_JID,
                "participant": PARTICIPANT_A,
                "fromMe": False,
            },
            "message": {
                "imageMessage": {
                    "url": "https://media.example.com/cupom.jpg",
                    "caption": "cupom mercado",
                }
            },
        },
    }


def _group_audio_payload():
    return {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {
                "remoteJid": GROUP_JID,
                "participant": PARTICIPANT_A,
                "fromMe": False,
            },
            "message": {"audioMessage": {"url": "https://media.example.com/audio.ogg"}},
        },
    }


async def _post_webhook(main, payload, path="/webhook"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://testserver",
    ) as client:
        return await client.post(path, json=payload)


def _configure_main(monkeypatch, main, allowed_group=GROUP_JID, secret=""):
    agent = AsyncMock()
    agent.process.return_value = "Gasto registrado"
    agent.process_image.return_value = "Imagem registrada"
    whatsapp = AsyncMock()
    whatsapp.send_text.return_value = True
    monkeypatch.setattr(main, "agent", agent)
    monkeypatch.setattr(main, "whatsapp", whatsapp)
    monkeypatch.setattr(main, "EVOLUTION_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(main, "ALLOWED_GROUP_JID", allowed_group)
    return agent, whatsapp


@pytest.mark.asyncio
async def test_webhook_ignores_private_text_message(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)

    response = await _post_webhook(main, _private_text_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "private_chat"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_ignores_unauthorized_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)

    response = await _post_webhook(main, _group_text_payload(group_jid=OTHER_GROUP_JID))

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "unauthorized_group"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_processes_authorized_group_text_and_replies_to_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)

    response = await _post_webhook(main, _group_text_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    agent.process.assert_awaited_once_with(
        phone="5541999999999",
        message="gastei 45 no ifood",
    )
    whatsapp.send_text.assert_awaited_once_with(
        phone=GROUP_JID,
        message="Gasto registrado",
    )


@pytest.mark.asyncio
async def test_webhook_ignores_from_me_in_authorized_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)
    payload = _group_text_payload()
    payload["data"]["key"]["fromMe"] = True

    response = await _post_webhook(main, payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "from_me"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_missing_allowed_group_fails_closed(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main, allowed_group="")

    response = await _post_webhook(main, _group_text_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "missing_allowed_group_jid"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_uses_distinct_participant_phones_in_same_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)

    first = await _post_webhook(main, _group_text_payload(participant=PARTICIPANT_A, text="gastei 50"))
    second = await _post_webhook(main, _group_text_payload(participant=PARTICIPANT_B, text="gastei 80"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert agent.process.await_args_list[0].kwargs["phone"] == "5541999999999"
    assert agent.process.await_args_list[1].kwargs["phone"] == "5541888888888"
    assert whatsapp.send_text.await_count == 2


@pytest.mark.asyncio
async def test_webhook_processes_authorized_group_image_and_replies_to_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)

    response = await _post_webhook(main, _group_image_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    agent.process_image.assert_awaited_once_with(
        phone="5541999999999",
        image_url="https://media.example.com/cupom.jpg",
        caption="cupom mercado",
    )
    whatsapp.send_text.assert_awaited_once_with(
        phone=GROUP_JID,
        message="Imagem registrada",
    )


@pytest.mark.asyncio
async def test_webhook_processes_authorized_group_audio_and_replies_to_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)
    monkeypatch.setattr(main, "process_audio", AsyncMock(return_value="gastei 30 no uber"))

    response = await _post_webhook(main, _group_audio_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    main.process_audio.assert_awaited_once_with("https://media.example.com/audio.ogg")
    agent.process.assert_awaited_once_with(
        phone="5541999999999",
        message="gastei 30 no uber",
    )
    whatsapp.send_text.assert_awaited_once_with(
        phone=GROUP_JID,
        message="Gasto registrado",
    )


@pytest.mark.asyncio
async def test_webhook_sends_audio_failure_message_to_group(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)
    monkeypatch.setattr(main, "process_audio", AsyncMock(return_value=None))

    response = await _post_webhook(main, _group_audio_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_awaited_once_with(
        phone=GROUP_JID,
        message="Não consegui entender o áudio 😅 Tente novamente ou manda por texto!",
    )


@pytest.mark.asyncio
async def test_webhook_ignores_unsupported_event(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main)

    response = await _post_webhook(main, {"event": "CONNECTION_UPDATE", "data": {}})

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "unsupported_event"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_secret(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main, secret="expected-secret")

    response = await _post_webhook(
        main,
        _group_text_payload(),
        path="/webhook?secret=wrong-secret",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid webhook secret"}
    agent.process.assert_not_awaited()
    whatsapp.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_accepts_valid_query_secret(monkeypatch):
    main = _load_main(monkeypatch)
    agent, whatsapp = _configure_main(monkeypatch, main, secret="expected-secret")

    response = await _post_webhook(
        main,
        _group_text_payload(),
        path="/webhook?secret=expected-secret",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    agent.process.assert_awaited_once()
    whatsapp.send_text.assert_awaited_once()
