import pytest

from app.services.webhook_normalizer import (
    is_group_jid,
    normalize_evolution_webhook,
    normalize_whatsapp_phone,
)


GROUP_JID = "120363012345678901@g.us"
PARTICIPANT = "5541999999999@s.whatsapp.net"


def test_normalizes_data_conversation_message():
    payload = {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {"remoteJid": "5541999999999@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "gastei 45 no ifood"},
        },
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.phone == "5541999999999"
    assert result.user_phone == "5541999999999"
    assert result.chat_jid == "5541999999999@s.whatsapp.net"
    assert result.reply_to == "5541999999999@s.whatsapp.net"
    assert result.is_group is False
    assert result.text == "gastei 45 no ifood"
    assert result.raw_event == "MESSAGES_UPSERT"


def test_normalizes_root_conversation_message():
    payload = {
        "event": "messages.upsert",
        "key": {"remoteJid": "5541888888888@s.whatsapp.net", "fromMe": False},
        "message": {"conversation": "recebi 100"},
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.phone == "5541888888888"
    assert result.user_phone == "5541888888888"
    assert result.text == "recebi 100"


def test_normalizes_extended_text_message():
    payload = {
        "event": "MESSAGES_UPSERT",
        "key": {"remoteJid": "5541777777777@s.whatsapp.net", "fromMe": False},
        "message": {"extendedTextMessage": {"text": "quanto gastei esse mes?"}},
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.text == "quanto gastei esse mes?"


def test_normalizes_group_message_with_data_key_participant():
    payload = {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {
                "remoteJid": GROUP_JID,
                "participant": PARTICIPANT,
                "fromMe": False,
            },
            "message": {"conversation": "gastei 50 no mercado"},
        },
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.chat_jid == GROUP_JID
    assert result.participant_jid == PARTICIPANT
    assert result.user_phone == "5541999999999"
    assert result.phone == "5541999999999"
    assert result.reply_to == GROUP_JID
    assert result.is_group is True
    assert result.text == "gastei 50 no mercado"


@pytest.mark.parametrize(
    ("path", "payload_part"),
    [
        ("key.participant", {"key": {"participant": PARTICIPANT}}),
        ("data.participant", {"data": {"participant": PARTICIPANT}}),
        ("participant", {"participant": PARTICIPANT}),
        ("data.sender", {"data": {"sender": PARTICIPANT}}),
        ("sender", {"sender": PARTICIPANT}),
    ],
)
def test_extracts_group_participant_from_alternative_fields(path, payload_part):
    payload = {
        "event": "MESSAGES_UPSERT",
        "key": {"remoteJid": GROUP_JID, "fromMe": False},
        "message": {"conversation": path},
    }
    for key, value in payload_part.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key].update(value)
        else:
            payload[key] = value

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.participant_jid == PARTICIPANT
    assert result.user_phone == "5541999999999"
    assert result.reply_to == GROUP_JID


def test_normalizes_individual_jid_suffixes():
    assert normalize_whatsapp_phone("5541999999999@s.whatsapp.net") == "5541999999999"
    assert normalize_whatsapp_phone("5541999999999@c.us") == "5541999999999"


def test_detects_group_jids_and_does_not_normalize_group_as_user_phone():
    assert is_group_jid(GROUP_JID) is True
    assert normalize_whatsapp_phone(GROUP_JID) is None


def test_ignores_group_message_without_participant():
    payload = {
        "event": "MESSAGES_UPSERT",
        "key": {"remoteJid": GROUP_JID, "fromMe": False},
        "message": {"conversation": "gastei 20"},
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is True
    assert result.chat_jid == GROUP_JID
    assert result.reply_to == GROUP_JID
    assert result.ignore_reason == "missing_participant"


def test_ignores_from_me_message():
    payload = {
        "event": "MESSAGES_UPSERT",
        "key": {"remoteJid": "5541999999999@s.whatsapp.net", "fromMe": True},
        "message": {"conversation": "mensagem propria"},
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is True
    assert result.from_me is True
    assert result.ignore_reason == "from_me"


def test_ignores_non_message_event():
    result = normalize_evolution_webhook({"event": "CONNECTION_UPDATE", "data": {}})

    assert result.ignored is True
    assert result.ignore_reason == "unsupported_event"


def test_ignores_missing_chat_jid():
    result = normalize_evolution_webhook(
        {"event": "MESSAGES_UPSERT", "message": {"conversation": "oi"}}
    )

    assert result.ignored is True
    assert result.ignore_reason == "missing_chat_jid"


def test_ignores_missing_content():
    result = normalize_evolution_webhook(
        {"event": "MESSAGES_UPSERT", "key": {"remoteJid": "5541999999999@s.whatsapp.net"}}
    )

    assert result.ignored is True
    assert result.phone == "5541999999999"
    assert result.user_phone == "5541999999999"
    assert result.ignore_reason == "missing_content"


def test_extracts_image_url_and_caption():
    payload = {
        "event": "MESSAGES_UPSERT",
        "key": {"remoteJid": "5541999999999@s.whatsapp.net"},
        "message": {
            "imageMessage": {
                "url": "https://media.example.com/image.jpg",
                "caption": "cupom",
            }
        },
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.image_url == "https://media.example.com/image.jpg"
    assert result.image_caption == "cupom"


def test_extracts_audio_url():
    payload = {
        "event": "MESSAGES_UPSERT",
        "key": {"remoteJid": "5541999999999@s.whatsapp.net"},
        "message": {"audioMessage": {"url": "https://media.example.com/audio.ogg"}},
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.audio_url == "https://media.example.com/audio.ogg"


def test_group_image_preserves_user_phone_and_reply_to():
    payload = {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {"remoteJid": GROUP_JID, "participant": PARTICIPANT},
            "message": {
                "imageMessage": {
                    "url": "https://media.example.com/image.jpg",
                    "caption": "cupom",
                }
            },
        },
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.user_phone == "5541999999999"
    assert result.reply_to == GROUP_JID
    assert result.image_url == "https://media.example.com/image.jpg"


def test_group_audio_preserves_user_phone_and_reply_to():
    payload = {
        "event": "MESSAGES_UPSERT",
        "data": {
            "key": {"remoteJid": GROUP_JID, "participant": PARTICIPANT},
            "message": {"audioMessage": {"url": "https://media.example.com/audio.ogg"}},
        },
    }

    result = normalize_evolution_webhook(payload)

    assert result.ignored is False
    assert result.user_phone == "5541999999999"
    assert result.reply_to == GROUP_JID
    assert result.audio_url == "https://media.example.com/audio.ogg"
