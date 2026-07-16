from app.services.webhook_normalizer import normalize_evolution_webhook


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


def test_ignores_missing_phone():
    result = normalize_evolution_webhook(
        {"event": "MESSAGES_UPSERT", "message": {"conversation": "oi"}}
    )

    assert result.ignored is True
    assert result.ignore_reason == "missing_phone"


def test_ignores_missing_content():
    result = normalize_evolution_webhook(
        {"event": "MESSAGES_UPSERT", "key": {"remoteJid": "5541999999999@s.whatsapp.net"}}
    )

    assert result.ignored is True
    assert result.phone == "5541999999999"
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
