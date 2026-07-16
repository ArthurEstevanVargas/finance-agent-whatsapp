from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
import logging
import os

from app.services.evolution import EvolutionService
from app.services.database import init_db, engine
from app.services.audio import process_audio
from app.services.webhook_normalizer import normalize_evolution_webhook
from app.agent.graph import FinanceAgent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVOLUTION_WEBHOOK_SECRET = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")

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


@app.post("/webhook")
async def webhook(request: Request):
    phone = None
    try:
        validate_webhook_secret(request)
        payload = await request.json()
        normalized = normalize_evolution_webhook(payload)

        logger.info(
            "Webhook Evolution recebido: event=%s ignored=%s reason=%s",
            normalized.raw_event,
            normalized.ignored,
            normalized.ignore_reason,
        )

        phone = normalized.phone
        if normalized.ignored:
            response = {"status": "ignored"}
            if normalized.ignore_reason:
                response["reason"] = normalized.ignore_reason
            return response

        if normalized.image_url:
            # Usuário mandou foto
            logger.info(f"🖼️ Imagem recebida de {phone}: {normalized.image_url}")

            response = await agent.process_image(
                phone=phone,
                image_url=normalized.image_url,
                caption=normalized.image_caption or "",
            )

        elif normalized.audio_url:
            # Usuário mandou áudio
            logger.info(f"🎙️ Áudio recebido de {phone}: {normalized.audio_url}")

            # Transcreve o áudio para texto
            transcribed_text = await process_audio(normalized.audio_url)

            if not transcribed_text:
                await whatsapp.send_text(
                    phone=phone,
                    message="Não consegui entender o áudio 😅 Tente novamente ou manda por texto!"
                )
                return {"status": "ok"}

            logger.info(f"📝 Áudio transcrito: {transcribed_text}")

            # Processa o texto transcrito normalmente
            response = await agent.process(phone=phone, message=transcribed_text)

        elif normalized.text:
            # Usuário mandou texto
            logger.info(f"📱 Mensagem de {phone}: {normalized.text}")
            response = await agent.process(phone=phone, message=normalized.text)

        else:
            return {"status": "ignored"}

        await whatsapp.send_text(phone=phone, message=response)
        return {"status": "ok"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        try:
            if phone:
                await whatsapp.send_text(
                    phone=phone,
                    message="Ops! 😅 Tive uma instabilidade aqui. Tente novamente em instantes 🙏"
                )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
