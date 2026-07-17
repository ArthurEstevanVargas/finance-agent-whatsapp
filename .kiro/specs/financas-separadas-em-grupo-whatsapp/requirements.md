# Requirements: Financas separadas em grupo WhatsApp autorizado

## Introduction

Esta especificacao define os requisitos para permitir que o `finance-agent-whatsapp` processe mensagens recebidas em um grupo especifico do WhatsApp, respondendo no proprio grupo e registrando as financas no historico individual do participante que enviou a mensagem.

Hoje o webhook normaliza o `remoteJid` como `phone` e esse mesmo identificador e usado tanto como chave do usuario financeiro quanto como destino da resposta. Esse comportamento funciona em conversas individuais, mas em grupos o `remoteJid` representa o grupo (`@g.us`) e nao o participante. A melhoria deve separar os conceitos de identidade financeira e chat de resposta, manter compatibilidade com a arquitetura atual baseada em FastAPI, Evolution API, LangGraph e SQLAlchemy, e evitar refatoracoes fora do necessario.

## 1. Objetivo

Permitir que dois ou mais participantes usem o mesmo grupo autorizado para controlar financas separadas, garantindo que cada comando financeiro seja processado com a chave do participante correto e que a resposta seja enviada para o grupo.

## 2. Problema atual

O webhook atual em `app/main.py` chama o `FinanceAgent` e o `EvolutionService` usando o mesmo campo `phone`. O normalizador em `app/services/webhook_normalizer.py` extrai esse valor principalmente de `remoteJid`. Em mensagens de grupo da Evolution API, `remoteJid` identifica o grupo, portanto usar esse valor como usuario financeiro mistura historicos e pode gravar transacoes na chave errada.

## 3. Comportamento desejado

Somente mensagens recebidas no grupo configurado devem ser processadas. Mensagens privadas e mensagens de grupos nao autorizados devem ser ignoradas por padrao nesta melhoria. Para mensagens do grupo autorizado, o sistema deve usar o participante como dono da acao financeira e o grupo como destino da resposta.

## 4. Variaveis de ambiente

- `ALLOWED_GROUP_JID`: JID completo do unico grupo autorizado, por exemplo `1203630xxxx@g.us`.
- `EVOLUTION_WEBHOOK_SECRET`: permanece como segredo opcional do webhook.
- `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE_NAME`: permanecem como configuracao de envio via Evolution API.

## 5. Modelo de dados/identidade

- `chat_jid`: identificador do chat de origem, normalmente `remoteJid`.
- `reply_to`: destino da resposta; para grupos deve ser igual ao `chat_jid` do grupo.
- `participant_jid`: JID do participante que enviou a mensagem no grupo.
- `user_phone`: chave normalizada do usuario financeiro, derivada do participante e sem sufixos como `@s.whatsapp.net` ou `@c.us`.
- `is_group`: booleano derivado do sufixo `@g.us` em `chat_jid`.
- `from_me`: booleano que preserva o comportamento atual de ignorar mensagens enviadas pelo proprio numero do agente.

O ID do grupo nunca deve ser usado como usuario financeiro. O `FinanceAgent` deve continuar recebendo a identidade do usuario financeiro, enquanto o envio de resposta deve usar `reply_to`.

## 6. Fluxo do webhook

1. O endpoint `POST /webhook` valida o segredo do webhook quando configurado.
2. O payload e normalizado para expor `chat_jid`, `participant_jid`, `user_phone`, `reply_to`, `is_group`, `text`, `image_url`, `audio_url`, `from_me`, `ignored` e `ignore_reason`.
3. Se `from_me=true`, o webhook retorna `ignored` e nao aciona o agente.
4. Se a mensagem nao for de grupo, o webhook retorna `ignored` por padrao nesta melhoria.
5. Se a mensagem for de grupo diferente de `ALLOWED_GROUP_JID`, o webhook retorna `ignored`.
6. Se a mensagem for do grupo autorizado, o webhook processa texto, imagem ou audio usando `user_phone` como usuario financeiro.
7. O webhook envia a resposta usando `reply_to`, preservando o JID do grupo.
8. Erros de processamento devem tentar responder no `reply_to` quando disponivel, sem trocar a identidade financeira pelo grupo.

## 7. Mudancas por arquivo

- `app/services/webhook_normalizer.py`: ampliar o dataclass normalizado, detectar grupo por `@g.us`, extrair participante por campos provaveis da Evolution API e normalizar `user_phone`.
- `app/main.py`: ler `ALLOWED_GROUP_JID`, ignorar mensagens privadas e grupos nao autorizados, chamar o agente com `user_phone` e enviar resposta para `reply_to`.
- `app/services/evolution.py`: avaliar e ajustar `_normalize_phone` para preservar JIDs de grupo com `@g.us` no envio, removendo sufixos somente de JIDs individuais.
- `.env.example`: adicionar `ALLOWED_GROUP_JID`.
- `README.md`: documentar a configuracao do grupo autorizado, o comportamento de mensagens privadas e a separacao entre usuario financeiro e chat de resposta.
- `tests/test_webhook_normalizer.py`, `tests/test_webhook.py` e `tests/test_evolution_service.py`: adicionar cobertura dos cenarios de grupo, participante, envio e midia.

## Requirements

### Requirement 1

**As a operador da aplicacao, I want autorizar apenas um grupo WhatsApp por variavel de ambiente, so that o agente financeiro nao responda fora do espaco combinado.**

#### Acceptance Criteria

1. WHEN `ALLOWED_GROUP_JID` estiver configurado, THEN o sistema SHALL processar somente mensagens cujo `chat_jid` seja exatamente igual a esse valor.
2. WHEN uma mensagem de grupo chegar com `chat_jid` diferente de `ALLOWED_GROUP_JID`, THEN o sistema SHALL ignorar a mensagem sem acionar o `FinanceAgent`.
3. WHEN uma mensagem privada chegar ao webhook, THEN o sistema SHALL ignora-la por padrao nesta melhoria.
4. IF `ALLOWED_GROUP_JID` estiver ausente em ambiente que recebe mensagens, THEN o sistema SHALL tratar mensagens de grupo como nao autorizadas ou falhar de forma clara, sem processar financas acidentalmente.
5. WHERE logs forem gerados para mensagens ignoradas, THEN o sistema SHALL registrar motivo e tipo de chat sem expor conteudo sensivel da mensagem.

### Requirement 2

**As a usuario participante de um grupo autorizado, I want que meus comandos financeiros usem minha identidade individual, so that meu historico nao seja misturado com o historico de outro participante.**

#### Acceptance Criteria

1. WHEN uma mensagem do grupo autorizado contiver participante valido, THEN o sistema SHALL derivar `user_phone` do JID do participante.
2. WHEN o participante for `5541999999999@s.whatsapp.net`, THEN o sistema SHALL normalizar `user_phone` para `5541999999999`.
3. WHEN o participante for `5541999999999@c.us`, THEN o sistema SHALL normalizar `user_phone` para `5541999999999`.
4. WHEN o `FinanceAgent` for chamado para texto, imagem ou audio, THEN o sistema SHALL passar `user_phone` como identificador financeiro.
5. IF `chat_jid` terminar com `@g.us`, THEN o sistema SHALL NOT usar `chat_jid` como `user_phone`.
6. WHEN dois participantes enviarem mensagens no mesmo grupo, THEN o sistema SHALL manter chaves financeiras distintas para cada participante.

### Requirement 3

**As a mantenedor da integracao Evolution API, I want normalizar campos de grupo e participante em um contrato interno estavel, so that variacoes do payload nao vazem para o webhook nem para o agente.**

#### Acceptance Criteria

1. WHEN o normalizador receber payload bruto da Evolution API, THEN o sistema SHALL expor `chat_jid`, `participant_jid`, `user_phone`, `reply_to`, `is_group`, `text`, `image_url`, `image_caption`, `audio_url`, `from_me`, `raw_event`, `ignored` e `ignore_reason`.
2. WHEN o payload contiver `data.key.remoteJid`, `key.remoteJid`, `data.remoteJid` ou `remoteJid`, THEN o sistema SHALL extrair o primeiro valor valido como `chat_jid`.
3. WHEN `chat_jid` terminar com `@g.us`, THEN o sistema SHALL marcar `is_group` como `true`.
4. WHEN `chat_jid` nao terminar com `@g.us`, THEN o sistema SHALL marcar `is_group` como `false`.
5. WHEN uma mensagem de grupo contiver participante em `data.key.participant`, `key.participant`, `data.participant`, `participant`, `data.sender` ou `sender`, THEN o sistema SHALL extrair o primeiro valor valido como `participant_jid`.
6. IF uma mensagem de grupo nao contiver participante valido, THEN o sistema SHALL ignorar a mensagem com motivo claro como `missing_participant`.
7. WHEN uma mensagem individual for normalizada, THEN o sistema MAY derivar `user_phone` do `chat_jid`, mas o webhook SHALL ignora-la por padrao nesta melhoria.
8. WHERE logs de validacao inicial forem adicionados, THEN o sistema SHOULD registrar campos principais como evento, `chat_jid`, presenca de participante, `is_group`, `from_me` e motivo de ignore, sem registrar segredos nem conteudo integral da mensagem.

### Requirement 4

**As a usuario participante de um grupo autorizado, I want receber a resposta do agente no grupo, so that a conversa financeira aconteca no mesmo chat onde enviei o comando.**

#### Acceptance Criteria

1. WHEN uma mensagem valida chegar do grupo autorizado, THEN o sistema SHALL definir `reply_to` como o JID do grupo.
2. WHEN o agente gerar resposta para texto, imagem ou audio, THEN o sistema SHALL chamar o envio WhatsApp usando `reply_to` como destino.
3. WHEN `reply_to` terminar com `@g.us`, THEN o `EvolutionService` SHALL preservar o JID do grupo para envio.
4. WHEN `_normalize_phone` receber JID individual com `@s.whatsapp.net` ou `@c.us`, THEN o sistema SHALL continuar removendo o sufixo para envio individual.
5. IF o envio de resposta falhar, THEN o sistema SHALL registrar erro operacional sem trocar o destino para `user_phone`.

### Requirement 5

**As a usuario participante de um grupo autorizado, I want que comandos e consultas financeiras usem somente meu proprio historico, so that as financas do casal fiquem separadas apesar do grupo compartilhado.**

#### Acceptance Criteria

1. WHEN o participante A enviar `gastei 50 no mercado`, THEN o sistema SHALL registrar a transacao na chave financeira do participante A.
2. WHEN o participante B enviar `gastei 80 na farmacia`, THEN o sistema SHALL registrar a transacao na chave financeira do participante B.
3. WHEN o participante A perguntar `quanto gastei esse mes?`, THEN o sistema SHALL consultar somente os dados associados ao participante A.
4. WHEN o participante B perguntar `quanto gastei esse mes?`, THEN o sistema SHALL consultar somente os dados associados ao participante B.
5. WHEN o onboarding for necessario, THEN o sistema SHALL executar onboarding por `user_phone` do participante e nao por `chat_jid` do grupo.
6. IF um participante ainda nao existir no banco, THEN o sistema SHALL criar ou iniciar o fluxo de usuario usando a chave normalizada do participante.

### Requirement 6

**As a operador da aplicacao, I want manter a protecao contra mensagens enviadas pelo proprio agente, so that o bot nao gere loops de resposta.**

#### Acceptance Criteria

1. WHEN o payload contiver `fromMe=true`, THEN o sistema SHALL ignorar a mensagem.
2. WHEN o payload contiver `key.fromMe=true` ou `data.key.fromMe=true`, THEN o sistema SHALL ignorar a mensagem.
3. IF uma mensagem for ignorada por `from_me`, THEN o sistema SHALL NOT acionar o `FinanceAgent`.
4. IF uma mensagem for ignorada por `from_me`, THEN o sistema SHALL NOT chamar `send_text`.
5. WHERE o retorno HTTP indicar mensagem ignorada, THEN o sistema SHOULD incluir motivo `from_me`.

### Requirement 7

**As a usuario do grupo autorizado, I want que texto, imagem e audio continuem funcionando, so that a melhoria de grupos nao reduza os tipos de entrada ja suportados.**

#### Acceptance Criteria

1. WHEN uma mensagem de texto valida chegar do grupo autorizado, THEN o sistema SHALL processar `text` com `FinanceAgent.process(user_phone, text)`.
2. WHEN uma imagem valida chegar do grupo autorizado, THEN o sistema SHALL processar `image_url` e `image_caption` com `FinanceAgent.process_image(user_phone, image_url, caption)`.
3. WHEN um audio valido chegar do grupo autorizado, THEN o sistema SHALL transcrever o audio e processar o texto transcrito com `FinanceAgent.process(user_phone, transcribed_text)`.
4. IF a transcricao de audio falhar, THEN o sistema SHALL enviar a mensagem de erro amigavel no `reply_to` do grupo.
5. WHEN texto, imagem ou audio forem processados no grupo autorizado, THEN a resposta final SHALL ser enviada para o grupo e nao para o participante em conversa privada.

### Requirement 8

**As a desenvolvedor do projeto, I want testes automatizados para identidade, autorizacao e envio em grupo, so that a separacao entre grupo e usuario financeiro nao regrida.**

#### Acceptance Criteria

1. WHEN os testes de webhook forem executados, THEN eles SHALL cobrir mensagem individual ignorada.
2. WHEN os testes de webhook forem executados, THEN eles SHALL cobrir grupo nao autorizado ignorado.
3. WHEN os testes de webhook forem executados, THEN eles SHALL cobrir grupo autorizado processado.
4. WHEN os testes de webhook forem executados, THEN eles SHALL verificar que o participante correto e usado como usuario financeiro.
5. WHEN os testes de webhook forem executados, THEN eles SHALL verificar que a resposta e enviada para o grupo.
6. WHEN os testes de webhook forem executados, THEN eles SHALL cobrir `fromMe=true` ignorado.
7. WHEN os testes de normalizador forem executados, THEN eles SHALL cobrir campos alternativos de participante como `data.key.participant`, `key.participant`, `data.participant`, `participant`, `data.sender` e `sender`.
8. WHEN os testes de midia forem executados, THEN eles SHALL cobrir imagem e audio em grupo mantendo o mesmo comportamento funcional de texto quanto a `user_phone` e `reply_to`.
9. WHEN os testes do `EvolutionService` forem executados, THEN eles SHALL verificar que JIDs de grupo com `@g.us` sao preservados para envio.

## 8. Casos de teste

- Mensagem individual com texto deve retornar `ignored` e nao chamar agente nem envio.
- Mensagem de grupo nao autorizado deve retornar `ignored` e nao chamar agente nem envio.
- Mensagem de grupo autorizado com `data.key.participant` deve chamar o agente com o telefone normalizado do participante.
- Mensagem de grupo autorizado deve chamar `send_text` com o JID do grupo como destino.
- Mensagem `fromMe=true` deve ser ignorada mesmo quando vier do grupo autorizado.
- Mensagens de dois participantes diferentes no mesmo grupo devem chamar o agente com chaves distintas.
- Consulta financeira feita por participante deve usar somente a chave desse participante.
- Imagem em grupo autorizado deve chamar `process_image` com `user_phone` e responder no grupo.
- Audio em grupo autorizado deve transcrever, processar com `user_phone` e responder no grupo.
- Falha de transcricao de audio deve enviar a mensagem de erro no grupo.
- Normalizador deve extrair participante dos campos alternativos mais provaveis da Evolution API.
- `EvolutionService` deve preservar `1203630xxxx@g.us` ao enviar resposta para grupo.

## 9. Criterios de aceite

1. O agente nao responde fora do grupo autorizado.
2. O agente responde dentro do grupo autorizado.
3. Dois participantes no mesmo grupo nao compartilham historico financeiro.
4. O ID do grupo nunca e usado como usuario financeiro.
5. O participante da mensagem e usado como chave do usuario no banco.
6. O app continua funcionando com texto, audio e imagem no grupo autorizado.
7. Mensagens privadas sao ignoradas por padrao nesta melhoria.
8. Mensagens `fromMe=true` continuam sendo ignoradas.
9. `.env.example` e `README.md` documentam `ALLOWED_GROUP_JID`.
10. Os testes automatizados passam.

## 10. Riscos e decisoes abertas

- A Evolution API pode variar o nome do campo do participante em grupos; a implementacao deve suportar os campos mais provaveis e facilitar adicionar novos campos com teste.
- O formato exato aceito pelo endpoint `sendText` para grupos deve ser validado na instancia real; a decisao inicial e preservar JIDs `@g.us` no envio.
- Mensagens privadas serao ignoradas por padrao nesta melhoria; reabilitar conversa individual deve ser tratado como mudanca separada para evitar ambiguidades de identidade.
- Logs de validacao inicial sao uteis para confirmar payloads reais, mas devem evitar registrar texto integral, imagens, audios, tokens, chaves ou dados financeiros sensiveis.
- A implementacao deve evitar refatorar o `FinanceAgent` e o modelo de banco alem do necessario, usando a chave `user_phone` ja esperada pelo fluxo atual.
