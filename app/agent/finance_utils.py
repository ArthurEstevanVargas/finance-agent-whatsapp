import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable

from app.models.transaction import Transaction, TransactionType


class QueryKind(str, Enum):
    SUMMARY = "summary"
    EXTRACT = "extract"
    LIST_INCOME = "list_income"
    LIST_EXPENSE = "list_expense"
    CATEGORY_DETAIL = "category_detail"
    INCOME_BY_SOURCE = "income_by_source"
    HELP = "help"


class CleanupTarget(str, Enum):
    ALL = "all"
    INCOME = "income"
    EXPENSE = "expense"


@dataclass(frozen=True)
class Period:
    label: str
    start: datetime
    end: datetime
    is_moving_window: bool = False


@dataclass(frozen=True)
class QueryRequest:
    kind: QueryKind
    period: Period
    transaction_type: TransactionType | None = None
    category: str | None = None
    text_filter: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class CleanupRequest:
    period: Period
    target: CleanupTarget


MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

NUMBER_WORDS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "três": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
}

CATEGORY_ALIASES = {
    "alimentacao": "Alimentação",
    "alimentação": "Alimentação",
    "comida": "Alimentação",
    "ifood": "Alimentação",
    "transporte": "Transporte",
    "uber": "Transporte",
    "moradia": "Moradia",
    "aluguel": "Moradia",
    "saude": "Saúde",
    "saúde": "Saúde",
    "lazer": "Lazer",
    "educacao": "Educação",
    "educação": "Educação",
    "salario": "Salário",
    "salário": "Salário",
    "freelance": "Freelance",
    "investimento": "Investimento",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def fmt_brl(value: float | None) -> str:
    amount = 0.0 if value is None else float(value)
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _parse_numeric_token(token: str) -> float | None:
    token = token.strip().replace(" ", "")
    if not token:
        return None

    if "." in token and "," in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        token = token.replace(",", ".")
    elif "." in token:
        parts = token.split(".")
        if len(parts[-1]) == 3 and all(len(part) == 3 for part in parts[1:]):
            token = token.replace(".", "")

    try:
        return float(token)
    except ValueError:
        return None


def parse_brl_amount(text: str) -> float | None:
    if not text:
        return None

    normalized = normalize_text(text)

    word_match = re.search(r"\b([a-z]+)\s+mil(?:\s+reais)?\b", normalized)
    if word_match:
        base = NUMBER_WORDS.get(word_match.group(1))
        if base is not None:
            return float(base * 1000)

    numeric_mil = re.search(r"\b(\d+(?:[,.]\d+)?)\s*mil\b", normalized)
    if numeric_mil:
        parsed = _parse_numeric_token(numeric_mil.group(1))
        if parsed is not None:
            return parsed * 1000

    money_match = re.search(r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{1,2}|\d+(?:[,.]\d{1,2})?)", normalized)
    if money_match:
        return _parse_numeric_token(money_match.group(1))

    return None


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    if month == 12:
        return start, datetime(year + 1, 1, 1)
    return start, datetime(year, month + 1, 1)


def resolve_period(message: str, now: datetime | None = None) -> Period:
    now = now or datetime.utcnow()
    text = normalize_text(message)

    if "ultimos 30 dias" in text or "ultimos trinta dias" in text:
        return Period("últimos 30 dias", now - timedelta(days=30), now, True)

    current_month_start = datetime(now.year, now.month, 1)

    if "mes passado" in text or "mês passado" in message.lower():
        previous_end = current_month_start
        previous_month = current_month_start.month - 1
        previous_year = current_month_start.year
        if previous_month == 0:
            previous_month = 12
            previous_year -= 1
        start, end = _month_bounds(previous_year, previous_month)
        return Period(f"{_month_name(previous_month)} de {previous_year}", start, end)

    for month_name, month in MONTHS.items():
        pattern = rf"\b{normalize_text(month_name)}(?:\s+de)?\s*(\d{{4}})?\b"
        match = re.search(pattern, text)
        if match:
            year = int(match.group(1)) if match.group(1) else now.year
            if not match.group(1) and month > now.month:
                year -= 1
            start, end = _month_bounds(year, month)
            return Period(f"{_month_name(month)} de {year}", start, end)

    return Period(f"{_month_name(now.month)} de {now.year}", current_month_start, now)


def _month_name(month: int) -> str:
    names = {
        1: "janeiro",
        2: "fevereiro",
        3: "março",
        4: "abril",
        5: "maio",
        6: "junho",
        7: "julho",
        8: "agosto",
        9: "setembro",
        10: "outubro",
        11: "novembro",
        12: "dezembro",
    }
    return names[month]


def parse_query_request(message: str, now: datetime | None = None) -> QueryRequest:
    period = resolve_period(message, now=now)
    text = normalize_text(message)

    if (
        "ajuda" in text
        or "help" in text
        or "comando" in text
        or "como usar" in text
        or "o que posso" in text
        or "consigo rodar" in text
    ):
        return QueryRequest(kind=QueryKind.HELP, period=period)

    if "extrato" in text:
        return QueryRequest(kind=QueryKind.EXTRACT, period=period, limit=100)

    if "salario" in text:
        return QueryRequest(
            kind=QueryKind.INCOME_BY_SOURCE,
            period=period,
            transaction_type=TransactionType.INCOME,
            category="Salário",
            text_filter="salário",
        )

    if "entrada" in text or "recebi" in text or "recebido" in text:
        return QueryRequest(kind=QueryKind.LIST_INCOME, period=period, transaction_type=TransactionType.INCOME)

    if "gasto" in text or "gastei" in text or "saida" in text or "saidas" in text:
        category = detect_category(message)
        if category:
            return QueryRequest(
                kind=QueryKind.CATEGORY_DETAIL,
                period=period,
                transaction_type=TransactionType.EXPENSE,
                category=category,
            )
        return QueryRequest(kind=QueryKind.LIST_EXPENSE, period=period, transaction_type=TransactionType.EXPENSE)

    category = detect_category(message)
    if category:
        return QueryRequest(
            kind=QueryKind.CATEGORY_DETAIL,
            period=period,
            transaction_type=TransactionType.EXPENSE,
            category=category,
        )

    return QueryRequest(kind=QueryKind.SUMMARY, period=period)


def is_cleanup_command(message: str) -> bool:
    text = normalize_text(message)
    action_terms = ("limpar", "apagar", "excluir", "deletar", "remover")
    object_terms = (
        "registro",
        "registros",
        "lancamento",
        "lancamentos",
        "despesa",
        "despesas",
        "gasto",
        "gastos",
        "entrada",
        "entradas",
    )
    return any(term in text for term in action_terms) and any(term in text for term in object_terms)


def parse_cleanup_request(message: str, now: datetime | None = None) -> CleanupRequest:
    text = normalize_text(message)
    period = resolve_period(message, now=now)
    if "entrada" in text or "entradas" in text:
        target = CleanupTarget.INCOME
    elif any(term in text for term in ("despesa", "despesas", "gasto", "gastos", "saida", "saidas")):
        target = CleanupTarget.EXPENSE
    else:
        target = CleanupTarget.ALL
    return CleanupRequest(period=period, target=target)


def cleanup_target_label(target: CleanupTarget) -> str:
    if target == CleanupTarget.INCOME:
        return "entradas"
    if target == CleanupTarget.EXPENSE:
        return "gastos"
    return "entradas e gastos"


def format_cleanup_confirmation(request: CleanupRequest, income_count: int, expense_count: int) -> str:
    total = income_count + expense_count
    lines = [
        f"Encontrei {total} lançamento(s) em {request.period.label}:",
        f"- Entradas: {income_count}",
        f"- Gastos: {expense_count}",
        "",
        f"Esta limpeza vai apagar {cleanup_target_label(request.target)} desse período.",
        "O orçamento mensal será mantido.",
        "",
        "Essa ação não pode ser desfeita.",
        'Responda "confirmar limpeza" para apagar ou "cancelar" para manter.',
    ]
    return "\n".join(lines)


def format_cleanup_result(request: CleanupRequest, deleted_count: int) -> str:
    return (
        "Limpeza concluída\n\n"
        f"Período: {request.period.label}\n"
        f"Itens apagados: {deleted_count}\n"
        "Orçamento mensal mantido."
    )


def detect_category(message: str) -> str | None:
    text = normalize_text(message)
    for alias, category in CATEGORY_ALIASES.items():
        if normalize_text(alias) in text:
            return category
    return None


def is_salary_like(category: str | None, description: str | None) -> bool:
    text = normalize_text(f"{category or ''} {description or ''}")
    return "salario" in text or "recorrente" in text


def format_transaction_confirmation(
    kind: TransactionType,
    amount: float | None,
    category: str | None,
    description: str | None,
) -> str:
    title = "Entrada registrada" if kind == TransactionType.INCOME else "Gasto registrado"
    return (
        f"{title}\n\n"
        f"Categoria: {category or 'Outros'}\n"
        f"Valor: {fmt_brl(amount)}\n"
        f"Descrição: {description or '-'}"
    )


def format_budget_updated(amount: float) -> str:
    return f"Orçamento atualizado\n\nNovo orçamento mensal: {fmt_brl(amount)}"


def format_help() -> str:
    return (
        "Comandos úteis:\n"
        "- registrar gasto: gastei 45 no iFood\n"
        "- registrar entrada: recebi 3200 de salário\n"
        "- ver resumo: resumo do mês\n"
        "- ver extrato: extrato deste mês\n"
        "- alterar orçamento: alterar orçamento para 5000\n"
        "- consultar categoria: quanto gastei com alimentação?\n"
        "- limpar mês: limpar gastos de julho"
    )


def format_summary_response(
    period: Period,
    monthly_budget: float | None,
    total_income: float,
    total_expense: float,
) -> str:
    balance = total_income - total_expense
    lines = [f"Resumo de {period.label}", ""]
    if monthly_budget is None:
        lines.append("Orçamento mensal: não cadastrado")
    else:
        lines.append(f"Orçamento mensal cadastrado: {fmt_brl(monthly_budget)}")
    lines.append(f"Entradas: {fmt_brl(total_income)}")
    lines.append(f"Gastos: {fmt_brl(total_expense)}")
    lines.append(f"Saldo: {fmt_brl(balance)}")
    if monthly_budget is not None:
        lines.append(f"Orçamento restante: {fmt_brl(monthly_budget - total_expense)}")
    return "\n".join(lines)


def format_transaction_list(
    title: str,
    transactions: Iterable[Transaction],
    empty_message: str,
    limit_reached: bool = False,
) -> str:
    items = list(transactions)
    lines = [title, ""]
    if not items:
        lines.append(empty_message)
    else:
        for t in items:
            date = t.created_at.strftime("%d/%m")
            description = f" - {t.description}" if t.description else ""
            lines.append(f"{date} - {t.category} - {fmt_brl(t.amount)}{description}")
    if limit_reached:
        lines.extend(["", "Há mais lançamentos além dos exibidos."])
    return "\n".join(lines)


def format_category_detail(period: Period, category: str, transactions: Iterable[Transaction]) -> str:
    items = list(transactions)
    total = sum(t.amount for t in items)
    lines = [f"Gastos com {category} em {period.label}", ""]
    if not items:
        lines.append("Não encontrei lançamentos para esse filtro.")
    else:
        for t in items:
            date = t.created_at.strftime("%d/%m")
            description = f" - {t.description}" if t.description else ""
            lines.append(f"{date} - {fmt_brl(t.amount)}{description}")
        lines.extend(["", f"Total: {fmt_brl(total)}"])
    return "\n".join(lines)


def format_extract(
    period: Period,
    incomes: Iterable[Transaction],
    expenses: Iterable[Transaction],
    monthly_budget: float | None,
) -> str:
    income_items = list(incomes)
    expense_items = list(expenses)
    total_income = sum(t.amount for t in income_items)
    total_expense = sum(t.amount for t in expense_items)
    balance = total_income - total_expense

    lines = [f"Extrato de {period.label}", "", "Entradas:"]
    if not income_items:
        lines.append("Nenhuma entrada registrada.")
    else:
        for t in income_items:
            label = t.description or t.category
            lines.append(f"{t.created_at.strftime('%d/%m')} - {label} - {fmt_brl(t.amount)}")

    lines.extend(["", "Gastos:"])
    if not expense_items:
        lines.append("Nenhum gasto registrado.")
    else:
        for t in expense_items:
            description = f" - {t.description}" if t.description else ""
            lines.append(f"{t.created_at.strftime('%d/%m')} - {t.category} - {fmt_brl(t.amount)}{description}")

    lines.extend(["", "Resumo:"])
    lines.append(f"Entradas: {fmt_brl(total_income)}")
    lines.append(f"Gastos: {fmt_brl(total_expense)}")
    lines.append(f"Saldo: {fmt_brl(balance)}")
    if monthly_budget is not None:
        lines.append(f"Orçamento restante: {fmt_brl(monthly_budget - total_expense)}")
    return "\n".join(lines)
