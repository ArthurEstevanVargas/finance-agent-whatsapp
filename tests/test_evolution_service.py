from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evolution import EvolutionService


@pytest.mark.asyncio
async def test_send_text_posts_to_evolution_endpoint_with_headers_and_payload():
    response = MagicMock()
    response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client

    with patch("app.services.evolution.httpx.AsyncClient", return_value=client_context) as async_client:
        service = EvolutionService(
            api_url="https://evolution.example.com/",
            api_key="secret-key",
            instance_name="finza",
            timeout=7.0,
        )

        result = await service.send_text("5541999999999@s.whatsapp.net", "Mensagem")

    assert result is True
    async_client.assert_called_once_with(timeout=7.0)
    client.post.assert_awaited_once_with(
        url="https://evolution.example.com/message/sendText/finza",
        headers={"ApiKey": "secret-key", "Content-Type": "application/json"},
        json={"number": "5541999999999", "text": "Mensagem"},
    )


@pytest.mark.asyncio
async def test_send_text_returns_false_for_http_error():
    import httpx

    request = httpx.Request("POST", "https://evolution.example.com/message/sendText/finza")
    response = httpx.Response(500, request=request, text="server error")

    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client

    with patch("app.services.evolution.httpx.AsyncClient", return_value=client_context):
        service = EvolutionService(
            api_url="https://evolution.example.com",
            api_key="secret-key",
            instance_name="finza",
        )

        result = await service.send_text("5541999999999", "Mensagem")

    assert result is False


@pytest.mark.asyncio
async def test_send_text_returns_false_when_required_config_is_missing():
    service = EvolutionService(api_url="", api_key="", instance_name="")

    with patch("app.services.evolution.httpx.AsyncClient") as async_client:
        result = await service.send_text("5541999999999", "Mensagem")

    assert result is False
    async_client.assert_not_called()
