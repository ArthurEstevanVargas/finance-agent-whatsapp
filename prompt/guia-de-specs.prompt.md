Leia o documento workflow/createSpec.prompt.md e gere o requirements.md com base na SPEC:

# SPEC: Migracao da Z-API para Evolution API

Data: 2026-07-16
Status: aprovado para planejamento tecnico

## Contexto

O projeto `finance-agent-whatsapp` recebe mensagens do WhatsApp via webhook, processa texto, imagem ou audio com o `FinanceAgent` e responde ao usuario pelo WhatsApp.

A integracao atual usa Z-API:

- `app/services/zapi.py` envia texto para `POST https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text`
- `app/main.py` recebe `POST /webhook` esperando payload plano da Z-API com campos como `phone`, `fromMe`, `text.message`, `image.imageUrl` e `audio.audioUrl`

A nova integracao deve consumir uma instancia da Evolution API ja criada e ja conectada ao WhatsApp no Railway. A aplicacao nao precisa criar instancia, gerar QR code ou parear o numero.

## Objetivos

- Substituir a dependencia da Z-API pela Evolution API com o menor impacto possivel no agente financeiro.
- Preservar o contrato interno de envio `send_text(phone, message)` para evitar mudancas no `FinanceAgent`.
- Adaptar o webhook da Evolution API para o formato interno esperado pela aplicacao.
- Documentar variaveis de ambiente, endpoints, autenticacao, payloads e criterios de aceite.

## Fora de Escopo

- Criar, conectar ou recriar instancia Evolution API pela aplicacao.
- Migrar banco interno do app para usar as tabelas da Evolution API.
- Implementar suporte a multiplas instancias WhatsApp.
- Manter Z-API e Evolution API ativas em paralelo depois da migracao.
- Reestruturar o grafo do agente financeiro.

## Decisao de Arquitetura

Usar um adapter compativel com o contrato atual.

Arquitetura alvo:

```text
WhatsApp -> Evolution API -> FastAPI /webhook
                              |
                              v
                     Webhook normalizer
                              |
                              v
                    FinanceAgent atual
                              |
                              v
              Evolution API /message/sendText/{instance}
```

Essa abordagem reduz o impacto porque a logica do agente continua recebendo `phone`, `message`, `image_url` e `audio_url` em um formato estavel. A diferenca entre Z-API e Evolution API fica isolada em servicos de gateway e normalizacao.

## Variaveis de Ambiente

Adicionar variaveis especificas para o app consumir a Evolution API:

```env
EVOLUTION_API_URL=https://sua-evolution.up.railway.app
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE_NAME=...
EVOLUTION_WEBHOOK_SECRET=...
```

Variaveis antigas a remover ou deixar sem uso apos a migracao:

```env
ZAPI_INSTANCE_ID
ZAPI_TOKEN
ZAPI_CLIENT_TOKEN
```

Observacoes:

- `AUTHENTICATION_API_KEY` e `DATABASE_CONNECTION_URI` pertencem a implantacao da Evolution API.
- O app deve usar `DATABASE_URL` para o banco do proprio agente financeiro.
- Evitar usar `SERVER_URL` no app para nao confundir URL da Evolution API com URL publica do FastAPI.
- `EVOLUTION_WEBHOOK_SECRET` deve proteger o endpoint `/webhook`, por header ou query string, se a Evolution API permitir configurar a URL com segredo.

## Autenticacao

### Z-API atual

Header:

```http
Client-Token: <ZAPI_CLIENT_TOKEN>
Content-Type: application/json
```

Endpoint contem `instanceId` e `token` na URL.

### Evolution API

Header obrigatorio:

```http
ApiKey: <EVOLUTION_API_KEY>
Content-Type: application/json
```

O nome da instancia entra no path do endpoint.

## Envio de Mensagens

### Contrato interno mantido

```python
await whatsapp.send_text(phone=phone, message=response)
```

### Z-API atual

```http
POST /send-text
```

Payload:

```json
{
  "phone": "5541999999999",
  "message": "Mensagem"
}
```

### Evolution API alvo

```http
POST /message/sendText/{instance}
```

Payload:

```json
{
  "number": "5541999999999",
  "text": "Mensagem"
}
```

Pontos de implementacao:

- Normalizar telefone antes do envio, removendo sufixos como `@s.whatsapp.net` quando existirem.
- Usar timeout HTTP explicito.
- Logar status e corpo de erro sem expor `ApiKey`.
- Retornar `False` em erro, mantendo comportamento atual do servico.

## Webhook

### Configuracao esperada na Evolution API

Configurar a instancia ja criada para chamar o FastAPI:

```http
POST /webhook/set/{instance}
```

Payload de configuracao sugerido:

```json
{
  "enabled": true,
  "url": "https://seu-app.up.railway.app/webhook?secret=<EVOLUTION_WEBHOOK_SECRET>",
  "webhookByEvents": false,
  "webhookBase64": false,
  "events": [
    "MESSAGES_UPSERT",
    "CONNECTION_UPDATE",
    "QRCODE_UPDATED"
  ]
}
```

Evento minimo para o agente funcionar:

- `MESSAGES_UPSERT`

Eventos uteis para observabilidade:

- `CONNECTION_UPDATE`
- `QRCODE_UPDATED`

### Normalizacao do payload de entrada

Criar uma camada que receba o payload bruto da Evolution API e produza um objeto interno com campos equivalentes ao contrato atual:

```json
{
  "phone": "5541999999999",
  "from_me": false,
  "text": "gastei 45 no ifood",
  "image_url": null,
  "image_caption": null,
  "audio_url": null,
  "raw_event": "MESSAGES_UPSERT"
}
```

Regras:

- Ignorar eventos que nao sejam mensagem recebida pelo usuario.
- Ignorar mensagens enviadas pelo proprio numero (`fromMe` ou `key.fromMe`).
- Extrair telefone de `data.key.remoteJid`, `key.remoteJid`, `sender`, `remoteJid` ou campo equivalente observado em payload real.
- Remover sufixos de JID, como `@s.whatsapp.net`.
- Extrair texto de campos como `message.conversation`, `message.extendedTextMessage.text` ou equivalente.
- Para imagem, buscar caption e URL/base64 disponiveis no payload.
- Para audio, buscar URL/base64 disponivel no payload.
- Se imagem ou audio vier apenas como base64, decidir na implementacao se o fluxo atual passa a aceitar arquivo temporario ou se a midia fica para uma segunda etapa.

## Impactos no Codigo

### `app/services/zapi.py`

Substituir por um servico Evolution API ou renomear para um nome neutro.

Opcoes:

- `app/services/evolution.py`, com classe `EvolutionService`
- `app/services/whatsapp.py`, com classe `WhatsAppService`

Recomendacao: `app/services/evolution.py` para deixar explicito o provedor usado.

### `app/main.py`

Mudancas esperadas:

- Trocar import de `ZAPIService` para `EvolutionService`.
- Trocar instancia `zapi` para `whatsapp` ou `evolution`.
- Aplicar normalizador no inicio do endpoint `/webhook`.
- Preservar o fluxo atual depois da normalizacao: texto, imagem, audio, chamada do agente e resposta.
- Validar `EVOLUTION_WEBHOOK_SECRET` quando configurado.

### `.env.example`

Atualizar variaveis para Evolution API e remover referencias a Z-API.

### `README.md`

Atualizar arquitetura, pre-requisitos, configuracao do webhook e variaveis de ambiente.

### Testes

Adicionar testes para:

- Envio de texto para endpoint `/message/sendText/{instance}` com header `ApiKey`.
- Normalizacao de payload `MESSAGES_UPSERT` com texto.
- Ignorar mensagem enviada pelo proprio numero.
- Ignorar eventos que nao sao mensagens.
- Validacao de segredo do webhook, se configurado.

## Riscos e Mitigacoes

### Payload real diferente dos exemplos documentados

Mitigacao: antes de finalizar suporte a texto, audio e imagem, capturar um payload real da instancia Evolution API em log controlado e ajustar o normalizador com testes.

### Midia sem URL publica

Mitigacao: manter texto como primeira etapa obrigatoria da migracao. Para audio/imagem, validar se a Evolution API entrega URL utilizavel pelo app atual ou se sera necessario baixar midia por endpoint especifico/base64.

### Confusao entre variaveis da Evolution API e variaveis do app

Mitigacao: prefixar variaveis consumidoras com `EVOLUTION_` e manter `DATABASE_URL` exclusivo para o banco do app.

### Webhook aberto publicamente

Mitigacao: usar `EVOLUTION_WEBHOOK_SECRET` na URL ou header e rejeitar chamadas invalidas com `401`.

### Regressao no agente

Mitigacao: manter o contrato interno normalizado e cobrir parser/servico com testes unitarios.

## Criterios de Aceite

- O app nao importa nem instancia `ZAPIService`.
- Nenhuma variavel `ZAPI_*` e necessaria para executar o app.
- `send_text(phone, message)` envia mensagem via `POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}`.
- Requests para Evolution API usam header `ApiKey`.
- `POST /webhook` processa mensagem de texto recebida da Evolution API e responde pelo WhatsApp.
- Mensagens enviadas pelo proprio numero sao ignoradas.
- Eventos que nao sao mensagens nao acionam o agente.
- Testes automatizados cobrem envio de texto e normalizacao de webhook.
- README e `.env.example` indicam Evolution API, nao Z-API.

## Plano de Validacao Manual

1. Configurar `.env` do app com `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE_NAME`, `DATABASE_URL` e `OPENAI_API_KEY`.
2. Configurar webhook na Evolution API para `https://<app>/webhook?secret=<secret>`.
3. Enviar mensagem de texto pelo WhatsApp para o numero conectado.
4. Confirmar nos logs que o evento recebido e `MESSAGES_UPSERT`.
5. Confirmar que o agente processa a mensagem e responde pelo WhatsApp.
6. Enviar uma mensagem a partir do proprio WhatsApp conectado e confirmar que ela e ignorada.
7. Testar audio e imagem, registrando o payload real para decidir se exigem adaptacao adicional.

## Sequencia Recomendada de Implementacao

1. Criar `EvolutionService` mantendo metodo `send_text(phone, message)`.
2. Criar normalizador de webhook Evolution API com testes.
3. Integrar normalizador e servico novo em `app/main.py`.
4. Atualizar `.env.example` e README.
5. Rodar testes automatizados.
6. Validar manualmente com payload real da instancia no Railway.
