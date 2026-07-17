from dataclasses import dataclass
from typing import Any


MESSAGE_EVENTS = {"MESSAGES_UPSERT", "messages.upsert"}
IGNORED_EVENTS = {
    "CONNECTION_UPDATE",
    "QRCODE_UPDATED",
    "MESSAGES_UPDATE",
    "MESSAGES_DELETE",
    "SEND_MESSAGE",
}
GROUP_JID_SUFFIX = "@g.us"
USER_JID_SUFFIXES = ("@s.whatsapp.net", "@c.us")


@dataclass(frozen=True)
class NormalizedWebhookMessage:
    phone: str | None
    chat_jid: str | None
    participant_jid: str | None
    user_phone: str | None
    reply_to: str | None
    is_group: bool
    from_me: bool
    text: str | None
    image_url: str | None
    image_caption: str | None
    audio_url: str | None
    raw_event: str | None
    ignored: bool
    ignore_reason: str | None = None


def _get_nested(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _first_value(payload: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _get_nested(payload, path)
        if value is not None:
            return value
    return None


def normalize_whatsapp_phone(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    if is_group_jid(normalized):
        return None

    for suffix in USER_JID_SUFFIXES:
        if suffix in normalized:
            normalized = normalized.split(suffix, 1)[0]
            break

    return normalized or None


def is_group_jid(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().endswith(GROUP_JID_SUFFIX)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _ignored(raw_event: str | None, reason: str, from_me: bool = False) -> NormalizedWebhookMessage:
    return NormalizedWebhookMessage(
        phone=None,
        chat_jid=None,
        participant_jid=None,
        user_phone=None,
        reply_to=None,
        is_group=False,
        from_me=from_me,
        text=None,
        image_url=None,
        image_caption=None,
        audio_url=None,
        raw_event=raw_event,
        ignored=True,
        ignore_reason=reason,
    )


def normalize_evolution_webhook(payload: dict[str, Any]) -> NormalizedWebhookMessage:
    raw_event = _first_value(payload, ("event", "type", "data.event"))

    if raw_event in IGNORED_EVENTS or (raw_event and raw_event not in MESSAGE_EVENTS):
        return _ignored(raw_event, "unsupported_event")

    from_me = _as_bool(
        _first_value(payload, ("fromMe", "key.fromMe", "data.fromMe", "data.key.fromMe"))
    )
    if from_me:
        return _ignored(raw_event, "from_me", from_me=True)

    chat_jid = _first_value(
        payload,
        (
            "data.key.remoteJid",
            "key.remoteJid",
            "data.remoteJid",
            "remoteJid",
            "data.sender",
            "sender",
        ),
    )
    chat_jid = str(chat_jid).strip() if chat_jid is not None else None
    if not chat_jid:
        return _ignored(raw_event, "missing_chat_jid")

    is_group = is_group_jid(chat_jid)
    participant_jid = None
    if is_group:
        participant_jid = _first_value(
            payload,
            (
                "data.key.participant",
                "key.participant",
                "data.participant",
                "participant",
                "data.sender",
                "sender",
            ),
        )
        participant_jid = str(participant_jid).strip() if participant_jid is not None else None
        if not participant_jid:
            return NormalizedWebhookMessage(
                phone=None,
                chat_jid=chat_jid,
                participant_jid=None,
                user_phone=None,
                reply_to=chat_jid,
                is_group=True,
                from_me=False,
                text=None,
                image_url=None,
                image_caption=None,
                audio_url=None,
                raw_event=raw_event,
                ignored=True,
                ignore_reason="missing_participant",
            )

    user_phone = normalize_whatsapp_phone(participant_jid if is_group else chat_jid)
    if not user_phone:
        return NormalizedWebhookMessage(
            phone=None,
            chat_jid=chat_jid,
            participant_jid=participant_jid,
            user_phone=None,
            reply_to=chat_jid,
            is_group=is_group,
            from_me=False,
            text=None,
            image_url=None,
            image_caption=None,
            audio_url=None,
            raw_event=raw_event,
            ignored=True,
            ignore_reason="missing_user_phone",
        )

    phone = user_phone
    reply_to = chat_jid

    text = _first_value(
        payload,
        (
            "data.message.conversation",
            "message.conversation",
            "data.message.extendedTextMessage.text",
            "message.extendedTextMessage.text",
        ),
    )
    image_url = _first_value(
        payload,
        (
            "data.message.imageMessage.url",
            "message.imageMessage.url",
            "data.image.imageUrl",
            "image.imageUrl",
            "data.image.url",
            "image.url",
        ),
    )
    image_caption = _first_value(
        payload,
        (
            "data.message.imageMessage.caption",
            "message.imageMessage.caption",
            "data.image.caption",
            "image.caption",
        ),
    )
    audio_url = _first_value(
        payload,
        (
            "data.message.audioMessage.url",
            "message.audioMessage.url",
            "data.audio.audioUrl",
            "audio.audioUrl",
            "data.audio.url",
            "audio.url",
        ),
    )

    text = str(text).strip() if text is not None else None
    image_url = str(image_url).strip() if image_url is not None else None
    image_caption = str(image_caption).strip() if image_caption is not None else None
    audio_url = str(audio_url).strip() if audio_url is not None else None

    if not any((text, image_url, audio_url)):
        return NormalizedWebhookMessage(
            phone=phone,
            chat_jid=chat_jid,
            participant_jid=participant_jid,
            user_phone=user_phone,
            reply_to=reply_to,
            is_group=is_group,
            from_me=False,
            text=None,
            image_url=None,
            image_caption=None,
            audio_url=None,
            raw_event=raw_event,
            ignored=True,
            ignore_reason="missing_content",
        )

    return NormalizedWebhookMessage(
        phone=phone,
        chat_jid=chat_jid,
        participant_jid=participant_jid,
        user_phone=user_phone,
        reply_to=reply_to,
        is_group=is_group,
        from_me=False,
        text=text,
        image_url=image_url,
        image_caption=image_caption,
        audio_url=audio_url,
        raw_event=raw_event,
        ignored=False,
    )
