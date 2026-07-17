from datetime import datetime

from app.agent.finance_utils import (
    QueryKind,
    fmt_brl,
    format_budget_updated,
    format_help,
    format_transaction_confirmation,
    parse_brl_amount,
    parse_query_request,
    resolve_period,
)
from app.models.transaction import TransactionType


def test_fmt_brl_formats_brazilian_currency():
    assert fmt_brl(4641.14) == "R$ 4.641,14"


def test_parse_brl_amount_supported_formats():
    assert parse_brl_amount("4641.14") == 4641.14
    assert parse_brl_amount("4.641,14") == 4641.14
    assert parse_brl_amount("R$ 4.641,14") == 4641.14
    assert parse_brl_amount("4641,14") == 4641.14
    assert parse_brl_amount("4 mil") == 4000.0
    assert parse_brl_amount("quatro mil reais") == 4000.0


def test_resolve_period_current_month():
    now = datetime(2026, 7, 17, 12, 0)
    period = resolve_period("resumo desse mês", now=now)

    assert period.start == datetime(2026, 7, 1)
    assert period.end == now
    assert period.is_moving_window is False


def test_resolve_period_previous_month():
    period = resolve_period("resumo do mês passado", now=datetime(2026, 7, 17, 12, 0))

    assert period.start == datetime(2026, 6, 1)
    assert period.end == datetime(2026, 7, 1)


def test_resolve_period_last_30_days():
    now = datetime(2026, 7, 17, 12, 0)
    period = resolve_period("últimos 30 dias", now=now)

    assert period.start == datetime(2026, 6, 17, 12, 0)
    assert period.end == now
    assert period.is_moving_window is True


def test_parse_query_request_kinds():
    assert parse_query_request("extrato deste mês").kind == QueryKind.EXTRACT
    assert parse_query_request("listar minhas entradas").kind == QueryKind.LIST_INCOME
    assert parse_query_request("listar meus gastos").kind == QueryKind.LIST_EXPENSE
    assert parse_query_request("quanto recebi de salário?").kind == QueryKind.INCOME_BY_SOURCE
    request = parse_query_request("quanto gastei com alimentação este mês?")
    assert request.kind == QueryKind.CATEGORY_DETAIL
    assert request.category == "Alimentação"


def test_fixed_templates_and_help():
    assert format_transaction_confirmation(
        TransactionType.EXPENSE,
        45,
        "Alimentação",
        "iFood",
    ) == "Gasto registrado\n\nCategoria: Alimentação\nValor: R$ 45,00\nDescrição: iFood"
    assert format_transaction_confirmation(
        TransactionType.INCOME,
        4041.14,
        "Salário",
        "salário",
    ).startswith("Entrada registrada")
    assert format_budget_updated(5000) == "Orçamento atualizado\n\nNovo orçamento mensal: R$ 5.000,00"
    help_text = format_help()
    assert "gastei 45 no iFood" in help_text
    assert "extrato deste mês" in help_text
    assert "alterar orçamento para 5000" in help_text
