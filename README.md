# Finza — Agente Financeiro Pessoal via WhatsApp

🌐 **Produto ao vivo:** [finza-landing-zp.vercel.app](https://finza-landing-zp.vercel.app)

> Controle financeiro pessoal por linguagem natural no WhatsApp — sem planilhas, sem apps, sem fricção.

Finza é um agente de IA que permite registrar gastos, entradas e comprovantes financeiros diretamente pelo WhatsApp, por texto, áudio ou foto. Construído com LangGraph para orquestração de agentes, GPT-4o para compreensão de linguagem natural e visão computacional, e Whisper para transcrição de áudio.

---

## Demonstração

| Entrada | Resposta |
|---|---|
| `"gastei 47 no mercado"` | 💸 Gasto registrado · Alimentação · R$ 47,00 |
| `"recebi 3200 de salário"` | 💰 Entrada registrada · Salário · R$ 3.200,00 |
| 🎤 áudio: `"paguei 40 na Netflix"` | 💸 Gasto registrado · Lazer · R$ 40,00 |
| 📸 foto do cupom fiscal | 💸 Extração automática de valor e categoria |
| `"quanto gastei esse mês?"` | 📊 Resumo com saldo e breakdown por categoria |
| `"detalha meus gastos em alimentação"` | 📋 Lista cada transação com data e valor |

---

## Funcionalidades

- **Linguagem natural** — entende o jeito que o usuário fala, sem comandos rígidos
- **Mensagens de voz** — transcrição automática via OpenAI Whisper
- **Foto de comprovante** — extração de valor e categoria via GPT-4o Vision
- **Resumos inteligentes** — consultas livres sobre gastos, categorias e saldo
- **Categorização automática** — Alimentação, Transporte, Lazer, Saúde e mais
- **Onboarding conversacional** — coleta nome e orçamento mensal na primeira interação
- **Sistema de trial e planos** — 7 dias grátis, com planos Mensal, Trimestral e Semestral
- **Histórico por usuário** — cada número de WhatsApp tem seu próprio contexto financeiro
- **Grupo autorizado** — permite usar um grupo específico compartilhado, mantendo o histórico separado por participante

---

## Arquitetura

O agente é implementado como um grafo de estados com LangGraph, onde cada nó tem uma responsabilidade isolada:

```
WhatsApp → Evolution API → FastAPI (Webhook)
                        ↓
                 [access_check]     ← valida trial / plano ativo
                        ↓
                  [onboarding]      ← coleta nome e orçamento (primeira vez)
                        ↓
           ┌────────────┴──────────────────┐
        texto                         imagem / áudio
           ↓                               ↓
      [classifier]               [image_extractor]
           ↓                     [audio → Whisper → texto → classifier]
   expense/income → [extractor] → [saver] → PostgreSQL
   query          → [query]              → Resumo financeiro
   unknown        → [fallback]           → Mensagem de ajuda
                        ↓
                  Evolution API → WhatsApp
```

**Decisões de design:**
- Cada nó do grafo é uma função pura com entrada e saída tipadas via `AgentState` (Pydantic)
- O nó `access_check` atua como middleware — bloqueia o fluxo se o trial expirou ou o plano está inativo
- Áudios em `.ogg` são convertidos para `.mp3` via `ffmpeg` antes da transcrição
- O nó `query` passa as últimas 20 transações individuais ao LLM, permitindo detalhamento por categoria
- A integração WhatsApp usa um adapter Evolution API e um normalizador de webhook para manter o `FinanceAgent` independente do provedor
- Em grupos, `remoteJid` identifica o chat de resposta e o participante da mensagem identifica o usuário financeiro

---

## Stack

| Tecnologia | Papel |
|---|---|
| [LangGraph](https://langchain-ai.github.io/langgraph/) | Orquestração do agente como grafo de estados |
| [OpenAI GPT-4o](https://openai.com/) | Classificação, extração de entidades e visão computacional |
| [OpenAI Whisper](https://openai.com/) | Transcrição de mensagens de voz |
| [FastAPI](https://fastapi.tiangolo.com/) | Servidor web e recepção de webhooks |
| [SQLAlchemy](https://www.sqlalchemy.org/) | ORM com modelos `User` e `Transaction` |
| [PostgreSQL](https://www.postgresql.org/) | Banco de dados relacional em produção |
| [Evolution API](https://evolution-api.com/) | Gateway de integração com WhatsApp |
| [Railway](https://railway.app/) | Deploy, hosting e banco gerenciado |
| [ffmpeg](https://ffmpeg.org/) | Conversão de áudio `.ogg` → `.mp3` |

---

## Estrutura do projeto

```
finance-agent-whatsapp/
├── app/
│   ├── agent/
│   │   ├── graph.py        # Grafo LangGraph + classe FinanceAgent
│   │   ├── nodes.py        # Nós: access_check, onboarding, classifier,
│   │   │                   #      extractor, image_extractor, saver, query, fallback
│   │   ├── prompts.py      # Prompts do LLM 
│   │   └── state.py        # AgentState (Pydantic) + enum MessageIntent
│   ├── models/
│   │   ├── transaction.py  # Model Transaction + enum TransactionType
│   │   └── user.py         # Model User + enums OnboardingStep e PlanStatus
│   ├── services/
│   │   ├── audio.py              # Download, conversão e transcrição de áudio
│   │   ├── database.py           # CRUD: usuários, transações e resumos
│   │   ├── evolution.py          # Envio de mensagens via Evolution API
│   │   └── webhook_normalizer.py # Normalização de webhooks Evolution API
│   └── main.py             # FastAPI + webhook POST /webhook
├── tests/
│   └── test_agent.py       # Testes unitários
├── .env.example
├── Dockerfile              # Inclui instalação do ffmpeg
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Como rodar localmente

**Pré-requisitos:** Python 3.11+, ffmpeg, PostgreSQL, conta OpenAI e uma instância Evolution API já criada e conectada ao WhatsApp.

```bash
# 1. Clone e entre no projeto
git clone https://github.com/matheussousamartins/finance-agent-whatsapp.git
cd finance-agent-whatsapp

# 2. Ambiente virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Dependências
pip install -r requirements.txt

# 4. Variáveis de ambiente
cp .env.example .env
# Edite .env com suas credenciais

# 5. Banco de dados (opcional, via Docker)
docker-compose up -d

# 6. Servidor
uvicorn app.main:app --reload

# 7. Exponha com ngrok
ngrok http 8000
# Configure a URL gerada na Evolution API:
# https://<seu-ngrok-ou-app>/webhook?secret=<EVOLUTION_WEBHOOK_SECRET>
```

**.env necessário:**
```env
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://user:password@localhost:5432/finza
EVOLUTION_API_URL=https://sua-evolution.up.railway.app
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE_NAME=...
EVOLUTION_WEBHOOK_SECRET=...
ALLOWED_GROUP_JID=1203630xxxx@g.us
```

`DATABASE_URL` pertence ao banco do agente financeiro. Variáveis internas da implantação da Evolution API, como `AUTHENTICATION_API_KEY` e `DATABASE_CONNECTION_URI`, não são usadas por este app.

### Grupo autorizado e identidade financeira

Nesta configuração, o webhook processa somente mensagens recebidas no grupo definido por `ALLOWED_GROUP_JID`. Mensagens privadas e mensagens de outros grupos são ignoradas por padrão.

Em mensagens de grupo, a Evolution API envia o grupo em `remoteJid` com sufixo `@g.us`. O app usa esse valor como `reply_to`, ou seja, o destino da resposta. A identidade financeira vem do participante da mensagem, em campos como `data.key.participant`, `key.participant`, `data.participant`, `participant`, `data.sender` ou `sender`.

Exemplo:

```text
chat_jid / reply_to: 1203630xxxx@g.us
participant_jid: 5541999999999@s.whatsapp.net
user_phone: 5541999999999
```

O `FinanceAgent` recebe `user_phone`, então `users.phone` e `transactions.phone` continuam representando o participante. O `EvolutionService` recebe `reply_to`, preservando o JID `@g.us` para envio da resposta ao grupo.

### Configuração do webhook na Evolution API

A instância Evolution API deve ser configurada fora da aplicação. O app não cria instância, não gera QR code e não pareia número.

Endpoint operacional da Evolution API:

```http
POST /webhook/set/{instance}
ApiKey: <EVOLUTION_API_KEY>
Content-Type: application/json
```

Payload sugerido:

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

Envio de respostas pelo app:

```http
POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}
ApiKey: <EVOLUTION_API_KEY>
Content-Type: application/json
```

```json
{
  "number": "5541999999999",
  "text": "Mensagem"
}
```

---

## Deploy

O projeto está configurado para deploy contínuo no **Railway** via `Dockerfile`. O `Dockerfile` instala o `ffmpeg` automaticamente — sem necessidade de configuração adicional.

```dockerfile
RUN apt-get update && apt-get install -y ffmpeg
```

As variáveis de ambiente são gerenciadas diretamente no painel do Railway. O banco PostgreSQL também é provisionado pelo Railway.

Para validar manualmente a integração:

1. Configure `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE_NAME`, `EVOLUTION_WEBHOOK_SECRET`, `ALLOWED_GROUP_JID`, `DATABASE_URL` e `OPENAI_API_KEY`.
2. Configure o webhook da Evolution API para `https://<app>/webhook?secret=<secret>`.
3. Envie uma mensagem de texto no grupo autorizado e confirme nos logs o evento `MESSAGES_UPSERT`.
4. Confirme que o agente processa a mensagem com o telefone do participante e responde no grupo.
5. Envie uma mensagem em conversa privada e confirme que ela é ignorada.
6. Envie uma mensagem em outro grupo e confirme que ela é ignorada.
7. Envie uma mensagem a partir do próprio WhatsApp conectado e confirme que ela é ignorada.
8. Envie comandos de dois participantes no mesmo grupo e confirme que os históricos financeiros ficam separados.
9. Teste áudio e imagem no grupo autorizado e registre o formato do payload real caso a Evolution API entregue mídia sem URL pública.

---

## Testes

```bash
pytest tests/ -v
```

---

## Sistema de planos

| Plano | Valor | Período |
|---|---|---|
| Trial | Grátis | 7 dias |
| Mensal | R$ 19,90 | 30 dias |
| Trimestral | R$ 49,90 | 90 dias |
| Semestral | R$ 89,90 | 180 dias |

---

## Licença

Proprietário — todos os direitos reservados. © 2026 Matheus Sousa Martins.
