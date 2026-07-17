# Requirements: Orcamento, entradas, saldo e extrato financeiro

## Introduction

Esta especificacao define os requisitos para melhorar a precisao financeira e o tom das respostas do `finance-agent-whatsapp`. O objetivo e separar corretamente os conceitos de orcamento mensal, entradas, gastos, saldo e orcamento disponivel; interpretar periodos de calendario de forma previsivel; permitir consultas detalhadas; atualizar o orcamento mensal por comando; reduzir emojis; e padronizar confirmacoes de registros.

Hoje o agente tende a confundir orcamento mensal com soma de entradas, usa "mes" como ultimos 30 dias, limita consultas as ultimas transacoes e deixa o LLM livre demais para formatar respostas. A melhoria deve preservar a arquitetura atual baseada em FastAPI, LangGraph, LangChain/OpenAI, SQLAlchemy e Evolution API, aproveitando o modelo de grafo de estado do LangGraph em que nos leem e atualizam o estado compartilhado.

## Requirements

### Requirement 1

**As a usuario financeiro, I want que orcamento, entradas, saldo e orcamento disponivel sejam conceitos separados, so that eu entenda minha situacao financeira sem misturar dinheiro recebido com limite planejado de gasto.**

#### Acceptance Criteria

1. WHEN o sistema calcular o orcamento mensal, THEN ele SHALL usar `User.monthly_budget` como limite planejado de gasto do usuario.
2. WHEN o sistema calcular entradas, THEN ele SHALL somar somente transacoes com tipo `income` no periodo solicitado.
3. WHEN o sistema calcular gastos, THEN ele SHALL somar somente transacoes com tipo `expense` no periodo solicitado.
4. WHEN o sistema calcular saldo, THEN ele SHALL retornar `entradas - gastos`.
5. WHEN o sistema calcular orcamento disponivel, THEN ele SHALL retornar `monthly_budget - gastos`.
6. IF `monthly_budget` estiver ausente, THEN o sistema SHALL informar que o orcamento mensal ainda nao foi cadastrado sem inferir o valor a partir das entradas.
7. WHEN o usuario pedir resumo financeiro, THEN a resposta SHALL diferenciar explicitamente orcamento mensal, entradas, gastos, saldo e orcamento restante quando esses dados forem relevantes.
8. WHEN entradas forem iguais ao orcamento mensal por coincidencia, THEN o sistema SHALL NOT tratar uma como fonte da outra.

### Requirement 2

**As a usuario financeiro, I want que consultas de "mes" usem mes calendario real, so that os numeros correspondam ao periodo que eu espero.**

#### Acceptance Criteria

1. WHEN o usuario disser "esse mes", "este mes" ou "resumo do mes", THEN o sistema SHALL usar o periodo do dia 1 do mes calendario atual ate o momento da consulta.
2. WHEN o usuario disser "mes passado", THEN o sistema SHALL usar o periodo completo do mes calendario anterior.
3. WHEN o usuario citar um mes especifico como "julho", THEN o sistema SHALL usar o periodo completo desse mes no ano mais provavel pela data atual ou pelo ano informado.
4. WHEN o usuario citar mes e ano, THEN o sistema SHALL usar o periodo completo daquele mes e ano.
5. WHEN o usuario pedir "ultimos 30 dias", THEN o sistema SHALL usar uma janela movel de 30 dias ate o momento da consulta.
6. IF o usuario nao informar periodo em uma consulta mensal, THEN o sistema SHOULD assumir o mes calendario atual.
7. WHERE uma consulta for respondida, THEN a resposta SHOULD deixar claro o periodo usado quando houver risco de ambiguidade.

### Requirement 3

**As a mantenedor do agente, I want que o no de consulta receba o orcamento mensal do usuario, so that o LLM responda com dados corretos sem inventar orcamento.**

#### Acceptance Criteria

1. WHEN `query_node` processar uma consulta, THEN o sistema SHALL buscar o usuario pelo identificador financeiro atual antes de montar o prompt.
2. WHEN o usuario existir, THEN o sistema SHALL incluir `monthly_budget` no contexto estruturado enviado ao LLM.
3. WHEN `monthly_budget` for nulo, THEN o sistema SHALL enviar esse estado explicitamente ao prompt de consulta.
4. WHEN o prompt de consulta for montado, THEN ele SHALL instruir o modelo a nao calcular nem inferir orcamento mensal a partir de entradas.
5. WHEN o prompt de consulta for montado, THEN ele SHALL incluir definicoes claras para entradas, gastos, saldo e orcamento disponivel.
6. IF a consulta puder ser respondida por calculo deterministico, THEN o sistema SHOULD calcular os totais no codigo antes de chamar o LLM.
7. WHERE o LangGraph atualizar o estado da consulta, THEN as atualizacoes SHALL permanecer compativeis com o modelo atual de nos que retornam alteracoes parciais do estado.

### Requirement 4

**As a usuario financeiro, I want respostas com tom profissional e poucos emojis, so that o assistente pareca um apoio financeiro confiavel.**

#### Acceptance Criteria

1. WHEN o agente responder por padrao, THEN a resposta SHALL usar linguagem direta, profissional e objetiva.
2. WHEN o agente responder por padrao, THEN a resposta SHALL conter zero emojis ou no maximo um emoji.
3. WHEN uma confirmacao de gasto for enviada, THEN o titulo SHOULD ser "Gasto registrado" em vez de uma frase festiva.
4. WHEN uma confirmacao de entrada for enviada, THEN o titulo SHOULD ser "Entrada registrada" em vez de uma frase festiva.
5. IF uma resposta de upgrade, erro ou ajuda exigir tom amigavel, THEN o sistema MAY usar linguagem cordial sem excesso de informalidade.
6. WHERE prompts do LLM controlarem estilo, THEN eles SHALL orientar o modelo a evitar emojis por padrao.

### Requirement 5

**As a usuario financeiro, I want confirmacoes padronizadas para gastos e entradas, so that eu veja sempre as mesmas informacoes em formato previsivel.**

#### Acceptance Criteria

1. WHEN um gasto for registrado com sucesso, THEN o sistema SHALL responder usando template fixo com titulo, categoria, valor e descricao.
2. WHEN uma entrada for registrada com sucesso, THEN o sistema SHALL responder usando template fixo com titulo, categoria, valor e descricao.
3. WHEN a descricao estiver vazia, THEN o sistema SHALL mostrar `-` no campo descricao.
4. WHEN valores forem exibidos, THEN o sistema SHALL formatar em BRL como `R$ 4.641,14`.
5. WHEN a categoria for exibida, THEN o sistema SHALL preservar a categoria escolhida pelo extrator ou pela regra de classificacao.
6. WHEN o registro for de gasto, THEN a resposta SHALL seguir este formato sem emojis obrigatorios:

```text
Gasto registrado

Categoria: Alimentacao
Valor: R$ 45,00
Descricao: iFood
```

7. WHEN o registro for de entrada, THEN a resposta SHALL seguir este formato sem emojis obrigatorios:

```text
Entrada registrada

Categoria: Salario
Valor: R$ 4.041,14
Descricao: salario
```

### Requirement 6

**As a usuario financeiro, I want consultas detalhadas de entradas e saidas com filtros fortes, so that eu consiga auditar minhas transacoes por periodo, tipo e categoria.**

#### Acceptance Criteria

1. WHEN o usuario pedir "listar minhas entradas", THEN o sistema SHALL listar transacoes do tipo `income` no periodo aplicavel.
2. WHEN o usuario pedir "listar meus gastos", THEN o sistema SHALL listar transacoes do tipo `expense` no periodo aplicavel.
3. WHEN o usuario pedir "mostrar extrato do mes", THEN o sistema SHALL retornar entradas e gastos separados para o mes calendario aplicavel.
4. WHEN o usuario pedir "detalhar gastos por categoria", THEN o sistema SHALL agrupar gastos por categoria no periodo aplicavel.
5. WHEN o usuario perguntar "quanto recebi de salario?", THEN o sistema SHALL filtrar entradas de categoria ou descricao relacionada a salario.
6. WHEN o usuario perguntar "quanto gastei com alimentacao este mes?", THEN o sistema SHALL filtrar gastos por categoria Alimentacao no mes calendario atual.
7. WHEN a consulta exigir filtros, THEN o sistema SHALL buscar transacoes pelo periodo, tipo e categoria necessarios em vez de depender apenas das 20 transacoes mais recentes.
8. IF nenhuma transacao corresponder aos filtros, THEN o sistema SHALL responder que nao encontrou lancamentos para o periodo e filtro solicitados.
9. WHERE transacoes individuais forem listadas, THEN cada item SHOULD conter data, categoria, valor e descricao quando disponivel.

### Requirement 7

**As a usuario financeiro, I want atualizar meu orcamento mensal por mensagem, so that eu nao dependa apenas do onboarding para corrigir meu limite de gastos.**

#### Acceptance Criteria

1. WHEN o usuario disser "alterar meu orcamento para 5000", THEN o sistema SHALL atualizar `User.monthly_budget` para 5000.
2. WHEN o usuario disser "meu novo orcamento mensal e 4800", THEN o sistema SHALL atualizar `User.monthly_budget` para 4800.
3. WHEN o usuario disser "meu orcamento e 5000", THEN o sistema SHALL classificar como atualizacao de orcamento quando o contexto indicar limite planejado de gasto.
4. WHEN o orcamento for atualizado, THEN o sistema SHALL NOT criar uma transacao de entrada.
5. WHEN o orcamento for atualizado com sucesso, THEN o sistema SHALL responder com confirmacao padronizada contendo o novo valor.
6. IF o usuario informar valor invalido para orcamento, THEN o sistema SHALL pedir o valor novamente com exemplo em formato brasileiro.
7. WHERE o classificador decidir a intencao, THEN ele SHALL ter uma intencao distinta para atualizacao de orcamento ou roteamento equivalente que nao confunda com `income`.

### Requirement 8

**As a usuario financeiro, I want ser alertado antes de duplicar salario ou entrada recorrente no mesmo mes, so that eu nao registre renda repetida por engano.**

#### Acceptance Criteria

1. WHEN o usuario tentar registrar uma entrada de categoria Salario com mesmo valor ja registrada no mes calendario atual, THEN o sistema SHALL alertar sobre possivel duplicidade antes de salvar a nova entrada.
2. WHEN o sistema detectar possivel duplicidade, THEN a mensagem SHALL informar categoria, valor e periodo da entrada ja encontrada.
3. WHEN o sistema detectar possivel duplicidade, THEN ele SHALL perguntar se o usuario deseja registrar outra mesmo assim.
4. IF o usuario confirmar a duplicidade, THEN o sistema SHALL registrar a nova entrada.
5. IF o usuario negar ou nao confirmar claramente, THEN o sistema SHALL NOT registrar a nova entrada.
6. WHEN a entrada recorrente nao tiver mesmo valor no mesmo mes, THEN o sistema SHALL seguir o fluxo normal de registro.
7. WHERE o estado de confirmacao for mantido, THEN ele SHALL ser associado ao usuario financeiro correto.

### Requirement 9

**As a usuario brasileiro, I want que valores monetarios em formatos comuns sejam entendidos, so that eu possa escrever naturalmente no WhatsApp.**

#### Acceptance Criteria

1. WHEN o usuario informar `4641.14`, THEN o sistema SHALL interpretar como 4641.14.
2. WHEN o usuario informar `4.641,14`, THEN o sistema SHALL interpretar como 4641.14.
3. WHEN o usuario informar `R$ 4.641,14`, THEN o sistema SHALL interpretar como 4641.14.
4. WHEN o usuario informar `4641,14`, THEN o sistema SHALL interpretar como 4641.14.
5. WHEN o usuario informar `4 mil`, THEN o sistema SHALL interpretar como 4000.00.
6. WHEN o usuario informar `quatro mil reais`, THEN o sistema SHALL interpretar como 4000.00.
7. WHEN o usuario informar valor no onboarding, THEN o sistema SHALL usar o mesmo parser monetario usado em registros e atualizacao de orcamento.
8. IF o valor for ambiguo ou impossivel de extrair, THEN o sistema SHALL pedir esclarecimento sem registrar transacao nem atualizar orcamento.
9. WHERE valores forem persistidos, THEN eles SHALL ser armazenados como numero decimal equivalente ao valor em reais.

### Requirement 10

**As a usuario financeiro, I want um modo extrato com entradas e gastos separados, so that eu consiga revisar o movimento do mes de forma organizada.**

#### Acceptance Criteria

1. WHEN o usuario pedir "extrato", "extrato deste mes" ou "mostrar extrato do mes", THEN o sistema SHALL retornar uma resposta de extrato.
2. WHEN o extrato for do mes atual, THEN o titulo SHALL indicar o mes calendario usado.
3. WHEN houver entradas no periodo, THEN o extrato SHALL listar entradas em uma secao propria.
4. WHEN houver gastos no periodo, THEN o extrato SHALL listar gastos em uma secao propria.
5. WHEN uma entrada for listada, THEN o item SHALL conter data, categoria ou descricao e valor.
6. WHEN um gasto for listado, THEN o item SHALL conter data, categoria, valor e descricao quando disponivel.
7. WHEN o resumo do extrato for exibido, THEN ele SHALL conter total de entradas, total de gastos, saldo e orcamento restante quando houver orcamento mensal cadastrado.
8. IF nao houver entradas ou gastos em uma secao, THEN o sistema SHALL mostrar uma linha indicando ausencia de lancamentos nessa secao.
9. WHERE valores forem exibidos no extrato, THEN eles SHALL usar formatacao BRL consistente.

### Requirement 11

**As a novo usuario, I want uma mensagem inicial que explique orcamento mensal como limite de gasto, so that eu nao confunda orcamento com entradas recebidas.**

#### Acceptance Criteria

1. WHEN o onboarding solicitar orcamento mensal, THEN a mensagem SHALL explicar que e o valor maximo que o usuario pretende gastar no mes.
2. WHEN o onboarding solicitar orcamento mensal, THEN a mensagem SHALL informar que entradas como salario, vale alimentacao e freelances podem ser registradas separadamente depois.
3. WHEN o onboarding validar o orcamento, THEN ele SHALL aceitar formatos monetarios brasileiros definidos nesta especificacao.
4. IF o usuario informar um valor invalido no onboarding, THEN a resposta SHALL usar tom profissional e exemplos validos.
5. WHERE a mensagem inicial mencionar funcionalidades, THEN ela SHALL diferenciar registrar gastos, registrar entradas, ver resumo e ver extrato.

### Requirement 12

**As a usuario financeiro, I want um comando de ajuda mais completo, so that eu saiba quais operacoes posso pedir ao agente.**

#### Acceptance Criteria

1. WHEN o usuario pedir "ajuda", "comandos" ou enviar mensagem nao reconhecida, THEN o sistema SHOULD retornar ajuda com comandos uteis.
2. WHEN a ajuda for exibida, THEN ela SHALL incluir exemplo de registro de gasto como "gastei 45 no iFood".
3. WHEN a ajuda for exibida, THEN ela SHALL incluir exemplo de registro de entrada como "recebi 3200 de salario".
4. WHEN a ajuda for exibida, THEN ela SHALL incluir exemplo de resumo como "resumo do mes".
5. WHEN a ajuda for exibida, THEN ela SHALL incluir exemplo de extrato como "extrato deste mes".
6. WHEN a ajuda for exibida, THEN ela SHALL incluir exemplo de alteracao de orcamento como "alterar orcamento para 5000".
7. WHEN a ajuda for exibida, THEN ela SHALL incluir exemplo de consulta por categoria como "quanto gastei com alimentacao?".
8. WHERE a ajuda for exibida, THEN ela SHALL seguir o tom profissional e a politica de poucos emojis.

### Requirement 13

**As a mantenedor do classificador, I want diferenciar frases ambiguas entre orcamento, entrada, consulta e gasto, so that o agente execute a acao correta.**

#### Acceptance Criteria

1. WHEN o usuario disser "meu orcamento e 5000", THEN o sistema SHALL classificar como atualizacao de orcamento.
2. WHEN o usuario disser "tenho 5000 para gastar", THEN o sistema SHALL classificar como atualizacao de orcamento ou definicao de limite planejado de gasto.
3. WHEN o usuario disser "recebi 5000", THEN o sistema SHALL classificar como registro de entrada.
4. WHEN o usuario disser "ganho 5000 por mes", THEN o sistema SHALL classificar como registro de entrada recorrente ou entrada de salario, conforme comportamento definido no design posterior, e SHALL NOT atualizar orcamento sem indicacao de limite de gasto.
5. WHEN o usuario disser "gastei 5000", THEN o sistema SHALL classificar como gasto.
6. WHEN o usuario fizer pergunta com "quanto", "listar", "mostrar", "resumo" ou "extrato", THEN o sistema SHALL classificar como consulta, salvo quando houver comando explicito de registro.
7. IF a frase continuar ambigua apos classificacao, THEN o sistema SHALL pedir confirmacao antes de salvar transacao ou atualizar orcamento.
8. WHERE o classificador usar LLM, THEN o prompt SHALL conter exemplos positivos e negativos para orcamento, entrada, consulta e gasto.

### Requirement 14

**As a desenvolvedor do projeto, I want funcoes de banco capazes de consultar por periodo, tipo e categoria, so that as respostas detalhadas nao dependam de amostras incompletas.**

#### Acceptance Criteria

1. WHEN o sistema precisar calcular resumo por periodo, THEN ele SHALL consultar transacoes entre `start_date` e `end_date`.
2. WHEN o sistema precisar listar entradas, THEN ele SHALL filtrar por `TransactionType.INCOME`.
3. WHEN o sistema precisar listar gastos, THEN ele SHALL filtrar por `TransactionType.EXPENSE`.
4. WHEN o sistema precisar consultar categoria, THEN ele SHALL aplicar filtro de categoria de forma case-insensitive.
5. WHEN o sistema precisar consultar descricao como salario, THEN ele SHOULD permitir filtro por descricao ou categoria.
6. IF o limite de listagem for aplicado, THEN a resposta SHALL indicar quando houver mais transacoes do que as exibidas.
7. WHERE consultas forem executadas, THEN elas SHALL respeitar o identificador financeiro do usuario atual.

### Requirement 15

**As a desenvolvedor do projeto, I want testes automatizados para os novos comportamentos financeiros, so that alteracoes em prompts, periodo e filtros nao regressem.**

#### Acceptance Criteria

1. WHEN os testes forem executados, THEN eles SHALL cobrir separacao entre `monthly_budget`, entradas, gastos, saldo e orcamento disponivel.
2. WHEN os testes forem executados, THEN eles SHALL cobrir "esse mes" como dia 1 ate hoje.
3. WHEN os testes forem executados, THEN eles SHALL cobrir "mes passado" como mes calendario anterior completo.
4. WHEN os testes forem executados, THEN eles SHALL cobrir "ultimos 30 dias" como janela movel somente quando solicitado.
5. WHEN os testes forem executados, THEN eles SHALL cobrir atualizacao de orcamento sem criacao de entrada.
6. WHEN os testes forem executados, THEN eles SHALL cobrir parser de valores para `4641.14`, `4.641,14`, `R$ 4.641,14`, `4641,14`, `4 mil` e `quatro mil reais`.
7. WHEN os testes forem executados, THEN eles SHALL cobrir templates padronizados de gasto e entrada.
8. WHEN os testes forem executados, THEN eles SHALL cobrir consulta de extrato com entradas, gastos e resumo separados.
9. WHEN os testes forem executados, THEN eles SHALL cobrir deteccao de possivel salario duplicado no mesmo mes.
10. WHEN os testes forem executados, THEN eles SHALL cobrir frases ambiguas do classificador listadas nesta especificacao.

## Casos de teste

- Usuario com `monthly_budget=4641.14`, entradas de R$ 4.641,14 e gastos de R$ 820,00 deve receber resumo informando orcamento mensal R$ 4.641,14, entradas R$ 4.641,14, gastos R$ 820,00, saldo R$ 3.821,14 e orcamento restante R$ 3.821,14.
- Consulta "resumo desse mes" deve considerar o periodo do dia 1 do mes atual ate hoje.
- Consulta "resumo do mes passado" deve considerar o mes calendario anterior completo.
- Consulta "ultimos 30 dias" deve usar janela movel de 30 dias.
- Mensagem "alterar meu orcamento para 5000" deve atualizar `monthly_budget` e nao criar transacao.
- Mensagem "recebi 5000" deve criar entrada e nao atualizar `monthly_budget`.
- Mensagem "gastei 45 no iFood" deve responder com template fixo de gasto.
- Mensagem "recebi 4041,14 de salario" deve responder com template fixo de entrada.
- Mensagem "listar minhas entradas" deve listar somente entradas no periodo aplicavel.
- Mensagem "listar meus gastos" deve listar somente gastos no periodo aplicavel.
- Mensagem "quanto recebi de salario?" deve filtrar entradas relacionadas a salario.
- Mensagem "quanto gastei com alimentacao este mes?" deve filtrar gastos de Alimentacao no mes atual.
- Mensagem "extrato deste mes" deve listar entradas e gastos em secoes separadas e mostrar resumo.
- Onboarding deve aceitar `R$ 4.641,14`, `4641,14`, `4 mil` e `quatro mil reais`.
- Tentativa de registrar salario de mesmo valor duas vezes no mesmo mes deve pedir confirmacao antes de salvar.

## Criterios de aceite

1. O agente nao confunde orcamento mensal com soma de entradas.
2. O agente calcula saldo como entradas menos gastos.
3. O agente calcula orcamento restante como orcamento mensal menos gastos.
4. Consultas de mes usam mes calendario real, exceto quando o usuario pedir ultimos 30 dias.
5. O prompt de consulta inclui `monthly_budget` e proibe inferencia de orcamento a partir de entradas.
6. Confirmacoes de gasto e entrada usam templates padronizados e tom profissional.
7. Consultas detalhadas usam filtros por periodo, tipo, categoria e descricao quando aplicavel.
8. O usuario consegue alterar orcamento mensal por comando sem criar entrada.
9. O agente alerta sobre possivel duplicidade de salario no mesmo mes.
10. Valores monetarios brasileiros sao extraidos de forma consistente no onboarding, registros e atualizacoes.
11. O modo extrato separa entradas e gastos e exibe resumo com saldo e orcamento restante.
12. A ajuda lista os principais comandos suportados.
13. O classificador diferencia orcamento, entrada, consulta e gasto em frases ambiguas.
14. Os testes automatizados relevantes passam.

## Riscos e decisoes abertas

- A confirmacao de duplicidade de salario pode exigir estado pendente entre mensagens; o design posterior deve decidir se esse estado fica no `AgentState`, em banco ou em outro mecanismo simples.
- A interpretacao de "ganho 5000 por mes" pode ser tratada como entrada unica ou recorrente; esta spec exige apenas que nao seja confundida com orcamento.
- Mes citado sem ano deve usar regra previsivel baseada na data atual; o design posterior deve fixar se usa o ano corrente ou o mes passado mais recente quando o mes ainda nao ocorreu no ano.
- Valores por extenso em portugues podem exigir parser deterministico, LLM ou abordagem hibrida; a implementacao deve priorizar testes para os exemplos exigidos.
- O modo extrato pode precisar limitar listas longas; quando limitar, deve informar que existem mais transacoes do que as exibidas.
