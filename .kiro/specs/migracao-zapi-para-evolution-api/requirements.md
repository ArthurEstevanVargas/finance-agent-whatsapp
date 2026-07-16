# Requirements: Migracao da Z-API para Evolution API

## Introduction

Esta especificacao define os requisitos para migrar a integracao WhatsApp do projeto `finance-agent-whatsapp` da Z-API para a Evolution API. O objetivo e substituir o provedor de envio e recebimento de mensagens com o menor impacto possivel no `FinanceAgent`, preservando o contrato interno `send_text(phone, message)` e normalizando os webhooks da Evolution API para o formato ja consumido pelo fluxo atual da aplicacao.

A instancia da Evolution API ja existe, ja esta conectada ao WhatsApp e esta hospedada no Railway. A aplicacao deve apenas consumir essa instancia para receber eventos via webhook e enviar respostas pelo endpoint de mensagens da Evolution API.

## Requirements

### Requirement 1

**As a desenvolvedor da aplicacao, I want substituir o servico Z-API por um servico Evolution API mantendo o contrato `send_text(phone, message)`, so that o `FinanceAgent` continue funcionando sem mudancas no seu fluxo principal.**

#### Acceptance Criteria

1. WHEN a aplicacao precisar enviar uma resposta ao usuario, THEN o sistema SHALL chamar um metodo interno `send_text(phone, message)` sem exigir alteracoes no `FinanceAgent`.
2. WHEN `send_text(phone, message)` for executado, THEN o sistema SHALL enviar uma requisicao `POST` para `{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}`.
3. WHEN a requisicao de envio for montada, THEN o sistema SHALL usar o payload JSON com os campos `number` e `text`.
4. WHEN a requisicao de envio for montada, THEN o sistema SHALL incluir o header `ApiKey` com o valor de `EVOLUTION_API_KEY`.
5. WHEN o telefone recebido contiver sufixos de JID como `@s.whatsapp.net`, THEN o sistema SHALL remover o sufixo antes de enviar a mensagem para a Evolution API.
6. IF a Evolution API retornar erro ou a chamada HTTP falhar, THEN o sistema SHALL retornar `False` mantendo o comportamento esperado do servico atual.
7. IF a Evolution API retornar erro, THEN o sistema SHALL registrar status e corpo da resposta sem expor o valor de `EVOLUTION_API_KEY`.
8. WHEN a chamada HTTP for realizada, THEN o sistema SHALL usar timeout explicito.

### Requirement 2

**As a mantenedor do projeto, I want remover a dependencia operacional da Z-API, so that a aplicacao dependa apenas da Evolution API para integracao WhatsApp.**

#### Acceptance Criteria

1. WHEN a aplicacao iniciar, THEN o sistema SHALL nao importar nem instanciar `ZAPIService`.
2. WHEN a aplicacao executar em ambiente configurado para Evolution API, THEN o sistema SHALL nao exigir variaveis `ZAPI_INSTANCE_ID`, `ZAPI_TOKEN` ou `ZAPI_CLIENT_TOKEN`.
3. WHEN o codigo de integracao WhatsApp for organizado, THEN o sistema SHALL usar um servico Evolution API explicito, preferencialmente em `app/services/evolution.py`.
4. IF referencias a Z-API permanecerem no codigo de execucao, THEN o sistema SHALL falhar nos criterios de aceite da migracao.
5. WHERE houver documentacao de configuracao da aplicacao, THEN o sistema SHALL substituir referencias operacionais da Z-API por referencias da Evolution API.

### Requirement 3

**As a aplicacao FastAPI, I want validar a configuracao de ambiente da Evolution API, so that falhas de configuracao sejam claras e nao se confundam com variaveis internas da instancia Evolution.**

#### Acceptance Criteria

1. WHEN a aplicacao configurar o cliente Evolution API, THEN o sistema SHALL ler `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE_NAME`.
2. IF `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` ou `EVOLUTION_INSTANCE_NAME` estiver ausente quando o envio de mensagens for usado, THEN o sistema SHALL reportar erro de configuracao de forma clara.
3. WHEN a aplicacao acessar seu banco proprio, THEN o sistema SHALL continuar usando `DATABASE_URL`.
4. WHERE variaveis como `AUTHENTICATION_API_KEY` e `DATABASE_CONNECTION_URI` existirem na infraestrutura, THEN o sistema SHALL trata-las como variaveis pertencentes a implantacao da Evolution API, nao ao app financeiro.
5. WHERE a URL publica da aplicacao FastAPI for documentada, THEN o sistema SHALL nao instruir o uso de `SERVER_URL` como variavel do app para evitar confusao com a Evolution API.

### Requirement 4

**As a usuario do WhatsApp, I want enviar mensagens de texto para o numero conectado, so that o agente financeiro processe a mensagem e responda pelo WhatsApp.**

#### Acceptance Criteria

1. WHEN a Evolution API enviar um evento `MESSAGES_UPSERT` para `POST /webhook`, THEN o sistema SHALL tentar normalizar o payload para o formato interno da aplicacao.
2. WHEN o payload normalizado representar uma mensagem de texto recebida de usuario, THEN o sistema SHALL acionar o fluxo atual do agente financeiro com o telefone e a mensagem extraida.
3. WHEN o agente financeiro gerar uma resposta, THEN o sistema SHALL enviar a resposta pelo metodo interno `send_text(phone, message)`.
4. IF o payload nao contiver texto, imagem ou audio aproveitavel, THEN o sistema SHALL nao acionar processamento financeiro indevido.
5. WHEN a resposta for enviada com sucesso, THEN o sistema SHALL manter o comportamento HTTP esperado do endpoint `/webhook`.

### Requirement 5

**As a desenvolvedor da integracao, I want normalizar payloads da Evolution API para um objeto interno estavel, so that diferencas do provedor fiquem isoladas fora do `FinanceAgent`.**

#### Acceptance Criteria

1. WHEN o normalizador receber payload bruto da Evolution API, THEN o sistema SHALL produzir um objeto interno contendo `phone`, `from_me`, `text`, `image_url`, `image_caption`, `audio_url` e `raw_event`.
2. WHEN o evento recebido nao for uma mensagem de usuario, THEN o sistema SHALL marcar o payload como ignoravel ou retornar resultado equivalente que impeça o acionamento do agente.
3. WHEN o payload contiver `data.key.remoteJid`, `key.remoteJid`, `sender`, `remoteJid` ou campo equivalente observado, THEN o sistema SHALL extrair o telefone a partir do primeiro campo valido disponivel.
4. WHEN o telefone extraido contiver sufixos como `@s.whatsapp.net`, THEN o sistema SHALL remover o sufixo no objeto normalizado.
5. WHEN o payload contiver texto em `message.conversation`, THEN o sistema SHALL extrair esse valor como texto da mensagem.
6. WHEN o payload contiver texto em `message.extendedTextMessage.text`, THEN o sistema SHALL extrair esse valor como texto da mensagem.
7. IF a Evolution API entregar estrutura equivalente para texto em payload real, THEN o sistema SHALL permitir ajuste do normalizador com teste automatizado correspondente.
8. WHEN a normalizacao for concluida para mensagem de texto, THEN o objeto normalizado SHALL ser compativel com o fluxo atual que espera `phone` e `message`.

### Requirement 6

**As a operador da aplicacao, I want ignorar mensagens enviadas pelo proprio numero conectado, so that o agente nao responda a si mesmo nem crie loops.**

#### Acceptance Criteria

1. WHEN o payload contiver `fromMe` igual a `true`, THEN o sistema SHALL ignorar a mensagem.
2. WHEN o payload contiver `key.fromMe` igual a `true`, THEN o sistema SHALL ignorar a mensagem.
3. IF uma mensagem for identificada como enviada pelo proprio numero, THEN o sistema SHALL nao acionar o `FinanceAgent`.
4. IF uma mensagem for identificada como enviada pelo proprio numero, THEN o sistema SHALL nao chamar `send_text`.
5. WHEN uma mensagem propria for ignorada, THEN o sistema SHOULD registrar log suficiente para diagnostico sem expor dados sensiveis desnecessarios.

### Requirement 7

**As a operador da aplicacao, I want ignorar eventos que nao sao mensagens recebidas, so that eventos operacionais da Evolution API nao acionem o agente financeiro.**

#### Acceptance Criteria

1. WHEN o webhook receber evento diferente de `MESSAGES_UPSERT`, THEN o sistema SHALL nao acionar o `FinanceAgent`.
2. WHEN o webhook receber evento `CONNECTION_UPDATE`, THEN o sistema SHALL tratar o evento como observabilidade e nao como mensagem de usuario.
3. WHEN o webhook receber evento `QRCODE_UPDATED`, THEN o sistema SHALL tratar o evento como observabilidade e nao como mensagem de usuario.
4. IF eventos nao suportados forem recebidos, THEN o sistema SHALL responder de forma controlada sem erro interno inesperado.
5. WHERE logs forem gerados para eventos ignorados, THEN o sistema SHALL preservar informacoes uteis como nome do evento sem registrar segredos.

### Requirement 8

**As a responsavel por seguranca, I want proteger o endpoint `/webhook` com segredo configuravel, so that chamadas publicas nao autorizadas sejam rejeitadas.**

#### Acceptance Criteria

1. WHEN `EVOLUTION_WEBHOOK_SECRET` estiver configurado, THEN o sistema SHALL validar o segredo recebido no webhook.
2. WHEN o segredo for enviado por query string, THEN o sistema SHALL aceitar a chamada somente se o valor corresponder a `EVOLUTION_WEBHOOK_SECRET`.
3. IF a Evolution API permitir envio por header e o sistema implementar essa opcao, THEN o sistema SHALL aceitar a chamada somente se o header corresponder a `EVOLUTION_WEBHOOK_SECRET`.
4. IF `EVOLUTION_WEBHOOK_SECRET` estiver configurado e a chamada nao apresentar segredo valido, THEN o sistema SHALL responder com `401`.
5. IF `EVOLUTION_WEBHOOK_SECRET` nao estiver configurado, THEN o sistema MAY aceitar chamadas sem segredo para ambientes locais ou de teste.
6. WHEN logs de autenticacao do webhook forem produzidos, THEN o sistema SHALL nao registrar o valor do segredo.

### Requirement 9

**As a usuario do WhatsApp, I want enviar imagem ou audio sem quebrar o webhook, so that a migracao preserve o caminho atual e identifique lacunas de midia da Evolution API.**

#### Acceptance Criteria

1. WHEN o payload da Evolution API contiver imagem com caption disponivel, THEN o sistema SHALL extrair a caption como `image_caption`.
2. WHEN o payload da Evolution API contiver URL publica de imagem disponivel, THEN o sistema SHALL preencher `image_url`.
3. WHEN o payload da Evolution API contiver URL publica de audio disponivel, THEN o sistema SHALL preencher `audio_url`.
4. IF imagem vier apenas como base64, THEN o sistema SHALL nao assumir URL publica inexistente.
5. IF audio vier apenas como base64, THEN o sistema SHALL nao assumir URL publica inexistente.
6. IF midia vier apenas como base64 e o fluxo atual nao suportar esse formato, THEN o sistema SHALL manter a migracao de texto funcional e registrar a necessidade de adaptacao posterior para midia.
7. WHEN payloads reais de imagem e audio forem capturados, THEN o sistema SHALL permitir ajuste do normalizador com testes baseados nesses payloads.

### Requirement 10

**As a desenvolvedor do projeto, I want testes automatizados para o novo gateway e o normalizador, so that a migracao tenha cobertura contra regressoes.**

#### Acceptance Criteria

1. WHEN os testes do servico Evolution API forem executados, THEN eles SHALL verificar que `send_text` chama `/message/sendText/{instance}`.
2. WHEN os testes do servico Evolution API forem executados, THEN eles SHALL verificar que o header `ApiKey` e enviado.
3. WHEN os testes do servico Evolution API forem executados, THEN eles SHALL verificar que o payload contem `number` e `text`.
4. WHEN os testes do normalizador forem executados com payload `MESSAGES_UPSERT` de texto, THEN eles SHALL verificar a extracao correta de telefone, texto e evento.
5. WHEN os testes do normalizador forem executados com mensagem enviada pelo proprio numero, THEN eles SHALL verificar que a mensagem e ignorada.
6. WHEN os testes do normalizador forem executados com evento que nao e mensagem, THEN eles SHALL verificar que o agente nao deve ser acionado.
7. IF `EVOLUTION_WEBHOOK_SECRET` estiver implementado no endpoint, THEN os testes SHALL cobrir chamada autorizada e chamada rejeitada com `401`.

### Requirement 11

**As a operador de deploy, I want documentacao atualizada para Evolution API, so that a configuracao em Railway e no app seja reproduzivel.**

#### Acceptance Criteria

1. WHEN `.env.example` for atualizado, THEN ele SHALL listar `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE_NAME` e `EVOLUTION_WEBHOOK_SECRET`.
2. WHEN `.env.example` for atualizado, THEN ele SHALL remover ou marcar como obsoletas as variaveis `ZAPI_INSTANCE_ID`, `ZAPI_TOKEN` e `ZAPI_CLIENT_TOKEN`.
3. WHEN o `README.md` for atualizado, THEN ele SHALL descrever a arquitetura `WhatsApp -> Evolution API -> FastAPI /webhook -> FinanceAgent -> Evolution API`.
4. WHEN o `README.md` for atualizado, THEN ele SHALL documentar o endpoint de envio `POST /message/sendText/{instance}` e o header `ApiKey`.
5. WHEN o `README.md` for atualizado, THEN ele SHALL documentar a configuracao sugerida de webhook na Evolution API para `POST /webhook/set/{instance}`.
6. WHEN o `README.md` for atualizado, THEN ele SHALL indicar que a instancia Evolution API ja deve existir e ja deve estar conectada ao WhatsApp.
7. WHERE a validacao manual for documentada, THEN o sistema SHALL incluir passos para enviar texto, confirmar `MESSAGES_UPSERT`, validar resposta, ignorar mensagem propria e testar audio/imagem.

### Requirement 12

**As a arquiteto do sistema, I want limitar o escopo da migracao, so that o trabalho nao reestruture componentes nao relacionados.**

#### Acceptance Criteria

1. WHEN a migracao for implementada, THEN o sistema SHALL nao criar, conectar ou recriar instancias da Evolution API.
2. WHEN a migracao for implementada, THEN o sistema SHALL nao gerar QR code nem parear numero WhatsApp pela aplicacao financeira.
3. WHEN a migracao for implementada, THEN o sistema SHALL nao migrar o banco interno do app para tabelas da Evolution API.
4. WHEN a migracao for implementada, THEN o sistema SHALL nao implementar suporte a multiplas instancias WhatsApp.
5. WHEN a migracao for implementada, THEN o sistema SHALL nao manter Z-API e Evolution API ativas em paralelo depois da migracao.
6. WHEN a migracao for implementada, THEN o sistema SHALL nao reestruturar o grafo do agente financeiro.

