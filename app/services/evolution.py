import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""

    normalized = str(phone).strip()
    if normalized.endswith("@g.us"):
        return normalized

    for suffix in ("@s.whatsapp.net", "@c.us"):
        if suffix in normalized:
            normalized = normalized.split(suffix, 1)[0]
            break

    return normalized


class EvolutionService:
    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        instance_name: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_url = (os.getenv("EVOLUTION_API_URL") if api_url is None else api_url or "").rstrip("/")
        self.api_key = os.getenv("EVOLUTION_API_KEY") if api_key is None else api_key
        self.instance_name = os.getenv("EVOLUTION_INSTANCE_NAME") if instance_name is None else instance_name
        self.api_key = self.api_key or ""
        self.instance_name = self.instance_name or ""
        self.timeout = timeout

    def _validate_config(self) -> bool:
        missing = []
        if not self.api_url:
            missing.append("EVOLUTION_API_URL")
        if not self.api_key:
            missing.append("EVOLUTION_API_KEY")
        if not self.instance_name:
            missing.append("EVOLUTION_INSTANCE_NAME")

        if missing:
            logger.error("Configuracao Evolution API incompleta: %s", ", ".join(missing))
            return False

        return True

    async def send_text(self, phone: str, message: str) -> bool:
        """Envia uma mensagem de texto via Evolution API."""
        if not self._validate_config():
            return False

        number = _normalize_phone(phone)
        url = f"{self.api_url}/message/sendText/{self.instance_name}"
        headers = {
            "ApiKey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "number": number,
            "text": message,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url=url, headers=headers, json=payload)
                response.raise_for_status()
                logger.info("Mensagem enviada para %s via Evolution API", number)
                return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "Erro HTTP ao enviar mensagem via Evolution API: %s - %s",
                e.response.status_code,
                e.response.text,
            )
            return False

        except Exception as e:
            logger.error("Erro inesperado ao enviar mensagem via Evolution API: %s", e)
            return False
