from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
import logging
import os

from app.services.evolution import EvolutionService
from app.services.database import init_db
from app.services.audio import process_audio
from app.services.webhook_normalizer import (
    NormalizedWebhookMessage,
    normalize_evolution_webhook,
)
from app.agent.graph import FinanceAgent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVOLUTION_WEBHOOK_SECRET = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")
ALLOWED_GROUP_JID = os.getenv("ALLOWED_GROUP_JID", "").strip()

app = FastAPI(
    title="Finance Agent WhatsApp",
    description="Agente financeiro pessoal via WhatsApp",
    version="1.0.0",
)

whatsapp = EvolutionService()
agent = FinanceAgent()


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("✅ Banco de dados inicializado")
    logger.info("🚀 Finance Agent WhatsApp rodando!")


@app.get("/")
async def root():
    return {"status": "ok", "message": "Finance Agent WhatsApp is running 💰"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


def validate_webhook_secret(request: Request) -> None:
    if not EVOLUTION_WEBHOOK_SECRET:
        return

    provided_secret = (
        request.query_params.get("secret")
        or request.headers.get("X-Webhook-Secret")
        or request.headers.get("X-Evolution-Webhook-Secret")
    )

    if provided_secret != EVOLUTION_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _ignored_response(reason: str | None = None) -> dict[str, str]:
    response = {"status": "ignored"}
    if reason:
        response["reason"] = reason
    return response


def _mask_jid(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value)
    if "@" not in value:
        return f"***{value[-4:]}" if len(value) > 4 else "***"
    local, domain = value.split("@", 1)
    masked_local = f"***{local[-4:]}" if len(local) > 4 else "***"
    return f"{masked_local}@{domain}"


def should_process_message(normalized: NormalizedWebhookMessage) -> tuple[bool, str | None]:
    if normalized.ignored:
        return False, normalized.ignore_reason
    if not normalized.is_group:
        return False, "private_chat"
    if not ALLOWED_GROUP_JID:
        return False, "missing_allowed_group_jid"
    if normalized.chat_jid != ALLOWED_GROUP_JID:
        return False, "unauthorized_group"
    if not normalized.user_phone:
        return False, "missing_user_phone"
    if not normalized.reply_to:
        return False, "missing_reply_to"
    return True, None


@app.post("/webhook")
async def webhook(request: Request):
    reply_to = None
    try:
        validate_webhook_secret(request)
        payload = await request.json()
        normalized = normalize_evolution_webhook(payload)

        logger.info(
            "Webhook Evolution recebido: event=%s ignored=%s reason=%s is_group=%s chat_jid=%s participant_present=%s",
            normalized.raw_event,
            normalized.ignored,
            normalized.ignore_reason,
            normalized.is_group,
            _mask_jid(normalized.chat_jid),
            bool(normalized.participant_jid),
        )

        should_process, ignore_reason = should_process_message(normalized)
        if not should_process:
            return _ignored_response(ignore_reason)

        user_phone = normalized.user_phone
        reply_to = normalized.reply_to
        if normalized.image_url:
            logger.info("Imagem recebida de user=%s chat=%s", user_phone, _mask_jid(reply_to))

            response = await agent.process_image(
                phone=user_phone,
                image_url=normalized.image_url,
                caption=normalized.image_caption or "",
            )

        elif normalized.audio_url:
            logger.info("Audio recebido de user=%s chat=%s", user_phone, _mask_jid(reply_to))

            transcribed_text = await process_audio(normalized.audio_url)

            if not transcribed_text:
                await whatsapp.send_text(
                    phone=reply_to,
                    message="Não consegui entender o áudio 😅 Tente novamente ou manda por texto!"
                )
                return {"status": "ok"}

            logger.info("Audio transcrito para user=%s", user_phone)
            response = await agent.process(phone=user_phone, message=transcribed_text)

        elif normalized.text:
            logger.info("Mensagem de texto recebida de user=%s chat=%s", user_phone, _mask_jid(reply_to))
            response = await agent.process(phone=user_phone, message=normalized.text)

        else:
            return {"status": "ignored"}

        await whatsapp.send_text(phone=reply_to, message=response)
        return {"status": "ok"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        try:
            if reply_to:
                await whatsapp.send_text(
                    phone=reply_to,
                    message="Ops! 😅 Tive uma instabilidade aqui. Tente novamente em instantes 🙏"
                )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
