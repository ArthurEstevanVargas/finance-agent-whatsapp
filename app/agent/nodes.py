import json
import logging
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.agent.state import AgentState, MessageIntent
from app.agent.finance_utils import (
    CleanupTarget,
    CleanupRequest,
    Period,
    QueryKind,
    detect_category,
    format_cleanup_confirmation,
    format_cleanup_result,
    fmt_brl,
    format_budget_updated,
    format_category_detail,
    format_extract,
    format_help,
    format_summary_response,
    format_transaction_confirmation,
    format_transaction_list,
    is_salary_like,
    is_cleanup_command,
    normalize_text,
    parse_brl_amount,
    parse_cleanup_request,
    parse_query_request,
    resolve_period,
)
from app.agent.prompts import (
    CLASSIFIER_PROMPT, EXTRACTOR_PROMPT, QUERY_PROMPT, IMAGE_EXTRACTOR_PROMPT,
    ONBOARDING_WELCOME_PROMPT, ONBOARDING_BUDGET_PROMPT,
    ONBOARDING_DONE_PROMPT, ONBOARDING_INVALID_BUDGET_PROMPT,
)
from app.models.transaction import TransactionType
from app.models.user import OnboardingStep, PlanStatus
from app.services.database import (
    save_transaction,
    get_user, create_user, update_user_name, update_user_budget,
    get_transactions, get_summary_for_period, find_possible_duplicate_income,
    count_transactions, delete_transactions,
    create_pending_confirmation, get_active_pending_confirmation,
    resolve_pending_confirmation,
)

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o", temperature=0)

UPGRADE_MESSAGE = """
⏰ *Seu período de teste encerrou!*

Para continuar usando o Finza, escolha um plano:

📅 *Mensal* — R$ 19,90/mês
📅 *Trimestral* — R$ 49,90 (economize R$ 9,80)
⭐ *Semestral* — R$ 89,90 (economize R$ 29,50)

👉 Fale comigo para assinar: https://wa.me/5541998216349

Qualquer dúvida é só falar! 😊
"""


# ─────────────────────────────────────────
# NÓ -1: Verificação de acesso
# Verifica se trial ou plano está ativo
# ─────────────────────────────────────────
def access_check_node(state: AgentState) -> AgentState:
    logger.info(f"🔐 Verificando acesso para {state.phone}")

    user = get_user(state.phone)

    # Usuário novo → deixa passar para o onboarding criar
    if not user:
        return AgentState(**{**state.model_dump(), "intent": None})

    # Onboarding ainda em andamento → deixa passar
    if user.onboarding_step != OnboardingStep.DONE:
        return AgentState(**{**state.model_dump(), "intent": None})

    # Tem acesso (trial ativo ou plano ativo) → deixa passar
    if user.has_access():
        # Avisa quantos dias restam no trial
        if user.plan_status == PlanStatus.TRIAL:
            from datetime import datetime
            days_left = 7 - (datetime.utcnow() - user.trial_start).days
            if days_left <= 2:
                logger.info(f"⚠️ Trial expirando em {days_left} dia(s) para {state.phone}")
        return AgentState(**{**state.model_dump(), "intent": None})

    # Sem acesso → bloqueia e manda mensagem de upgrade
    logger.info(f"🚫 Acesso bloqueado para {state.phone}")
    return AgentState(**{**state.model_dump(), "response": UPGRADE_MESSAGE})


# ─────────────────────────────────────────
# NÓ 0: Onboarding
# Verifica se usuário existe e coleta dados
# ─────────────────────────────────────────
def onboarding_node(state: AgentState) -> AgentState:
    logger.info(f"👋 Verificando onboarding para {state.phone}")

    user = get_user(state.phone)

    # Usuário novo → cria e envia boas-vindas
    if not user:
        create_user(state.phone)
        return AgentState(**{**state.model_dump(), "response": ONBOARDING_WELCOME_PROMPT})

    # Aguardando nome
    if user.onboarding_step == OnboardingStep.WAITING_NAME:
        name = state.message.strip().title()
        update_user_name(state.phone, name)
        response = ONBOARDING_BUDGET_PROMPT.replace("{name}", name)
        return AgentState(**{**state.model_dump(), "response": response})

    # Aguardando orçamento
    if user.onboarding_step == OnboardingStep.WAITING_BUDGET:
        budget = parse_brl_amount(state.message)
        if budget is None:
            return AgentState(**{**state.model_dump(), "response": ONBOARDING_INVALID_BUDGET_PROMPT})
        update_user_budget(state.phone, budget)
        response = (
            ONBOARDING_DONE_PROMPT
            .replace("{name}", user.name or "")
            .replace("{budget}", fmt_brl(budget))
        )
        return AgentState(**{**state.model_dump(), "response": response})

    # Onboarding já concluído → segue fluxo normal
    return AgentState(**{**state.model_dump(), "intent": None})


# ─────────────────────────────────────────
# NÓ 1A: Confirmação pendente
# Resolve confirmações de duplicidade antes de classificar nova intenção
# ─────────────────────────────────────────
def pending_confirmation_node(state: AgentState) -> AgentState:
    pending = get_active_pending_confirmation(state.phone)
    if not pending:
        return AgentState(**{**state.model_dump(), "intent": None})

    text = normalize_text(state.message).strip()
    if pending.action_type == "monthly_cleanup":
        if text == "confirmar limpeza":
            payload = json.loads(pending.payload_json)
            transaction_type = (
                TransactionType(payload["transaction_type"])
                if payload.get("transaction_type")
                else None
            )
            deleted_count = delete_transactions(
                phone=state.phone,
                start_date=datetime.fromisoformat(payload["start_date"]),
                end_date=datetime.fromisoformat(payload["end_date"]),
                transaction_type=transaction_type,
            )
            resolve_pending_confirmation(pending.id, "resolved")
            cleanup_request = CleanupRequest(
                period=Period(
                    label=payload["period_label"],
                    start=datetime.fromisoformat(payload["start_date"]),
                    end=datetime.fromisoformat(payload["end_date"]),
                ),
                target=CleanupTarget(payload["target"]),
            )
            response = format_cleanup_result(cleanup_request, deleted_count)
            return AgentState(**{**state.model_dump(), "response": response})

        if text in {"cancelar", "cancela", "não", "nao", "n"}:
            resolve_pending_confirmation(pending.id, "cancelled")
            return AgentState(**{**state.model_dump(), "response": "Limpeza cancelada."})

        if is_cleanup_command(state.message) or any(keyword in text for keyword in ("gastei", "paguei", "recebi", "orcamento", "orçamento", "resumo", "extrato")):
            return AgentState(**{**state.model_dump(), "intent": None})

        response = 'Você tem uma limpeza pendente. Responda "confirmar limpeza" para apagar ou "cancelar" para manter.'
        return AgentState(**{**state.model_dump(), "response": response})

    affirmative = {"sim", "s", "yes", "pode registrar", "registrar mesmo assim"}
    negative = {"nao", "não", "n", "cancelar"}

    if text in affirmative:
        payload = json.loads(pending.payload_json)
        transaction_type = TransactionType(payload["transaction_type"])
        save_transaction(
            phone=state.phone,
            type=transaction_type,
            amount=payload["amount"],
            category=payload["category"],
            description=payload.get("description"),
        )
        resolve_pending_confirmation(pending.id, "resolved")
        response = format_transaction_confirmation(
            transaction_type,
            payload["amount"],
            payload["category"],
            payload.get("description"),
        )
        return AgentState(**{**state.model_dump(), "response": response})

    if text in negative:
        resolve_pending_confirmation(pending.id, "cancelled")
        return AgentState(**{**state.model_dump(), "response": "Registro cancelado."})

    if is_cleanup_command(state.message) or any(keyword in text for keyword in ("gastei", "paguei", "recebi", "orcamento", "orçamento", "resumo", "extrato")):
        return AgentState(**{**state.model_dump(), "intent": None})

    response = 'Você tem um registro pendente. Responda "sim" para registrar ou "não" para cancelar.'
    return AgentState(**{**state.model_dump(), "response": response})


# ─────────────────────────────────────────
# NÓ 1: Classificador
# Decide o que o usuário quer fazer
# ─────────────────────────────────────────
def classifier_node(state: AgentState) -> AgentState:
    logger.info(f"🔍 Classificando mensagem: {state.message}")

    message_text = normalize_text(state.message)
    if is_cleanup_command(state.message):
        logger.info("✅ Intenção detectada por regra: cleanup")
        return AgentState(**{**state.model_dump(), "intent": MessageIntent.CLEANUP})

    help_keywords = ("ajuda", "help", "comando", "como usar", "o que posso", "consigo rodar")
    if any(keyword in message_text for keyword in help_keywords):
        logger.info("✅ Intenção detectada por regra: query")
        return AgentState(**{**state.model_dump(), "intent": MessageIntent.QUERY})

    query_keywords = ("quanto", "qual", "listar", "mostrar", "resumo", "extrato")
    if (
        any(keyword in message_text for keyword in query_keywords)
        or "meu salario" in message_text
        or "minha renda" in message_text
    ):
        logger.info("✅ Intenção detectada por regra: query")
        return AgentState(**{**state.model_dump(), "intent": MessageIntent.QUERY})

    prompt = CLASSIFIER_PROMPT.format(message=state.message)
    response = llm.invoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()

    if intent not in ["expense", "income", "query", "update_budget", "cleanup"]:
        intent = MessageIntent.UNKNOWN

    logger.info(f"✅ Intenção detectada: {intent}")
    return AgentState(**{**state.model_dump(), "intent": intent})


# ─────────────────────────────────────────
# NÓ 2: Extrator de texto
# Extrai valor, categoria e descrição da mensagem
# ─────────────────────────────────────────
def extractor_node(state: AgentState) -> AgentState:
    logger.info(f"📦 Extraindo dados da mensagem: {state.message}")

    prompt = EXTRACTOR_PROMPT.replace("{message}", state.message)
    response = llm.invoke([HumanMessage(content=prompt)])

    try:
        raw = response.content.strip()
        logger.info(f"🔍 Resposta bruta do extrator: {raw}")

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)
        transaction_type = (
            TransactionType.INCOME if state.intent == "income" else TransactionType.EXPENSE
        )
        parsed_amount = parse_brl_amount(state.message)
        amount = parsed_amount if parsed_amount is not None else data.get("amount", 0.0)
        return AgentState(**{
            **state.model_dump(),
            "amount": amount,
            "category": data.get("category", "Outros"),
            "description": data.get("description", ""),
            "transaction_type": transaction_type,
        })
    except json.JSONDecodeError:
        logger.error(f"❌ Erro ao parsear JSON do extrator: {response.content}")
        parsed_amount = parse_brl_amount(state.message) or 0.0
        transaction_type = (
            TransactionType.INCOME if state.intent == "income" else TransactionType.EXPENSE
        )
        return AgentState(**{
            **state.model_dump(),
            "amount": parsed_amount,
            "category": "Outros",
            "description": "",
            "transaction_type": transaction_type,
        })


# ─────────────────────────────────────────
# NÓ 2B: Extrator de imagem
# Extrai dados financeiros de foto de comprovante
# ─────────────────────────────────────────
def image_extractor_node(state: AgentState) -> AgentState:
    logger.info(f"🖼️ Extraindo dados da imagem: {state.image_url}")

    try:
        response = llm.invoke([
            HumanMessage(content=[
                {"type": "text", "text": IMAGE_EXTRACTOR_PROMPT},
                {"type": "image_url", "image_url": {"url": state.image_url}},
            ])
        ])

        raw = response.content.strip()
        logger.info(f"🔍 Resposta bruta do extrator de imagem: {raw}")

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)
        return AgentState(**{
            **state.model_dump(),
            "amount": data.get("amount", 0.0),
            "category": data.get("category", "Outros"),
            "description": data.get("description", ""),
            "transaction_type": TransactionType.EXPENSE,
        })

    except Exception as e:
        logger.error(f"❌ Erro ao processar imagem: {e}")
        return AgentState(**{
            **state.model_dump(),
            "amount": 0.0,
            "category": "Outros",
            "description": "erro ao processar imagem",
            "transaction_type": TransactionType.EXPENSE,
        })


# ─────────────────────────────────────────
# NÓ 2C: Checagem de duplicidade de entrada recorrente
# ─────────────────────────────────────────
def duplicate_income_check_node(state: AgentState) -> AgentState:
    if state.transaction_type != TransactionType.INCOME:
        return AgentState(**state.model_dump())
    if not is_salary_like(state.category, state.description):
        return AgentState(**state.model_dump())
    if state.amount is None:
        return AgentState(**state.model_dump())

    period = resolve_period("esse mês")
    duplicate = find_possible_duplicate_income(
        phone=state.phone,
        amount=state.amount,
        start_date=period.start,
        end_date=period.end,
        category=state.category or "",
        description=state.description,
    )
    if not duplicate:
        return AgentState(**state.model_dump())

    create_pending_confirmation(
        phone=state.phone,
        action_type="duplicate_income",
        payload={
            "transaction_type": TransactionType.INCOME.value,
            "amount": state.amount,
            "category": state.category or "Salário",
            "description": state.description or "",
        },
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    response = (
        f"Você já registrou uma entrada de {state.category or 'Salário'} "
        f"de {fmt_brl(state.amount)} neste mês.\n"
        'Deseja registrar outra mesmo assim? Responda "sim" para registrar ou "não" para cancelar.'
    )
    return AgentState(**{**state.model_dump(), "response": response})


# ─────────────────────────────────────────
# NÓ 2D: Atualização de orçamento
# ─────────────────────────────────────────
def budget_update_node(state: AgentState) -> AgentState:
    amount = parse_brl_amount(state.message)
    if amount is None:
        return AgentState(**{**state.model_dump(), "response": ONBOARDING_INVALID_BUDGET_PROMPT})

    update_user_budget(state.phone, amount, complete_onboarding=False)
    return AgentState(**{**state.model_dump(), "response": format_budget_updated(amount)})


# ─────────────────────────────────────────
# NÓ 2E: Limpeza mensal de lançamentos
# ─────────────────────────────────────────
def monthly_cleanup_node(state: AgentState) -> AgentState:
    request = parse_cleanup_request(state.message)
    transaction_type = None
    if request.target == CleanupTarget.INCOME:
        transaction_type = TransactionType.INCOME
    elif request.target == CleanupTarget.EXPENSE:
        transaction_type = TransactionType.EXPENSE

    income_count = 0
    expense_count = 0
    if transaction_type in (None, TransactionType.INCOME):
        income_count = count_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.INCOME,
        )
    if transaction_type in (None, TransactionType.EXPENSE):
        expense_count = count_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.EXPENSE,
        )

    total = income_count + expense_count
    if total == 0:
        response = f"Não encontrei lançamentos para limpar em {request.period.label}."
        return AgentState(**{**state.model_dump(), "response": response})

    create_pending_confirmation(
        phone=state.phone,
        action_type="monthly_cleanup",
        payload={
            "message": state.message,
            "start_date": request.period.start.isoformat(),
            "end_date": request.period.end.isoformat(),
            "period_label": request.period.label,
            "target": request.target.value,
            "transaction_type": transaction_type.value if transaction_type else None,
        },
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    response = format_cleanup_confirmation(request, income_count, expense_count)
    return AgentState(**{**state.model_dump(), "response": response})


# ─────────────────────────────────────────
# NÓ 3: Salvar transação
# Persiste no banco e gera resposta de confirmação
# ─────────────────────────────────────────
def saver_node(state: AgentState) -> AgentState:
    logger.info(f"💾 Salvando transação: {state.amount} - {state.category}")

    save_transaction(
        phone=state.phone,
        type=state.transaction_type,
        amount=state.amount,
        category=state.category,
        description=state.description,
    )

    response = format_transaction_confirmation(
        state.transaction_type,
        state.amount,
        state.category,
        state.description,
    )

    return AgentState(**{**state.model_dump(), "response": response})


# ─────────────────────────────────────────
# NÓ 4: Consulta
# Busca resumo no banco e responde o usuário
# ─────────────────────────────────────────
def query_node(state: AgentState) -> AgentState:
    logger.info(f"📊 Consultando resumo para {state.phone}")

    user = get_user(state.phone)
    request = parse_query_request(state.message)
    summary = get_summary_for_period(state.phone, request.period.start, request.period.end)
    monthly_budget = user.monthly_budget if user else None

    if request.kind == QueryKind.HELP:
        return AgentState(**{**state.model_dump(), "response": format_help()})

    if request.kind == QueryKind.EXTRACT:
        incomes = get_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.INCOME,
            limit=request.limit,
        )
        expenses = get_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.EXPENSE,
            limit=request.limit,
        )
        response = format_extract(request.period, incomes, expenses, monthly_budget)
        return AgentState(**{**state.model_dump(), "response": response})

    if request.kind == QueryKind.LIST_INCOME:
        transactions = get_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.INCOME,
            limit=request.limit + 1,
        )
        limit_reached = len(transactions) > request.limit
        response = format_transaction_list(
            f"Entradas de {request.period.label}",
            transactions[:request.limit],
            "Não encontrei entradas nesse período.",
            limit_reached,
        )
        return AgentState(**{**state.model_dump(), "response": response})

    if request.kind == QueryKind.LIST_EXPENSE:
        transactions = get_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.EXPENSE,
            limit=request.limit + 1,
        )
        limit_reached = len(transactions) > request.limit
        response = format_transaction_list(
            f"Gastos de {request.period.label}",
            transactions[:request.limit],
            "Não encontrei gastos nesse período.",
            limit_reached,
        )
        return AgentState(**{**state.model_dump(), "response": response})

    if request.kind == QueryKind.CATEGORY_DETAIL:
        transactions = get_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.EXPENSE,
            category=request.category,
            limit=request.limit,
        )
        response = format_category_detail(request.period, request.category or "categoria", transactions)
        return AgentState(**{**state.model_dump(), "response": response})

    if request.kind == QueryKind.INCOME_BY_SOURCE:
        transactions = get_transactions(
            phone=state.phone,
            start_date=request.period.start,
            end_date=request.period.end,
            transaction_type=TransactionType.INCOME,
            category=request.category,
            text_filter=request.text_filter or request.category,
            limit=request.limit,
        )
        total = sum(t.amount for t in transactions)
        response = format_transaction_list(
            f"Entradas de {request.category or 'fonte'} em {request.period.label}",
            transactions,
            "Não encontrei entradas para esse filtro.",
        )
        if transactions:
            response = f"{response}\n\nTotal: {fmt_brl(total)}"
        return AgentState(**{**state.model_dump(), "response": response})

    response = format_summary_response(
        request.period,
        monthly_budget,
        summary["total_income"],
        summary["total_expense"],
    )
    return AgentState(**{**state.model_dump(), "response": response})


# ─────────────────────────────────────────
# NÓ 5: Fallback
# Responde quando não entende a mensagem
# ─────────────────────────────────────────
def fallback_node(state: AgentState) -> AgentState:
    return AgentState(**{**state.model_dump(), "response": format_help()})
