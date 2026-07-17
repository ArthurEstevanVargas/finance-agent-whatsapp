import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta
import json

from app.agent.nodes import (
    budget_update_node,
    classifier_node,
    duplicate_income_check_node,
    extractor_node,
    fallback_node,
    pending_confirmation_node,
    query_node,
    saver_node,
)
from app.agent.state import AgentState
from app.agent.graph import FinanceAgent
from app.models.transaction import Base
from app.models.transaction import TransactionType
from app.services import database


# ─────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────

@pytest.fixture
def expense_state():
    return AgentState(phone="5541999999999", message="gastei 45 no ifood")

@pytest.fixture
def income_state():
    return AgentState(phone="5541999999999", message="recebi 3200 de salário")

@pytest.fixture
def query_state():
    return AgentState(phone="5541999999999", message="quanto gastei esse mês?")

@pytest.fixture
def unknown_state():
    return AgentState(phone="5541999999999", message="oi tudo bem?")


def _setup_in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def _create_ready_user(phone="5541999999999", budget=3000):
    database.create_user(phone)
    database.update_user_name(phone, "Teste")
    database.update_user_budget(phone, budget)


# ─────────────────────────────────────────
# TESTES: CLASSIFIER NODE
# ─────────────────────────────────────────

class TestClassifierNode:

    @patch("app.agent.nodes.llm")
    def test_classifica_expense(self, mock_llm, expense_state):
        mock_llm.invoke.return_value = MagicMock(content="expense")
        result = classifier_node(expense_state)
        assert result.intent == "expense"

    @patch("app.agent.nodes.llm")
    def test_classifica_income(self, mock_llm, income_state):
        mock_llm.invoke.return_value = MagicMock(content="income")
        result = classifier_node(income_state)
        assert result.intent == "income"

    @patch("app.agent.nodes.llm")
    def test_classifica_query(self, mock_llm, query_state):
        mock_llm.invoke.return_value = MagicMock(content="query")
        result = classifier_node(query_state)
        assert result.intent == "query"

    @patch("app.agent.nodes.llm")
    def test_classifica_unknown(self, mock_llm, unknown_state):
        mock_llm.invoke.return_value = MagicMock(content="unknown")
        result = classifier_node(unknown_state)
        assert result.intent == "unknown"

    @patch("app.agent.nodes.llm")
    def test_classifica_update_budget(self, mock_llm):
        mock_llm.invoke.return_value = MagicMock(content="update_budget")
        result = classifier_node(AgentState(phone="5541999999999", message="alterar orçamento para 5000"))
        assert result.intent == "update_budget"

    @patch("app.agent.nodes.llm")
    def test_resposta_invalida_vira_unknown(self, mock_llm, expense_state):
        """Se o LLM retornar algo inesperado, deve virar unknown."""
        mock_llm.invoke.return_value = MagicMock(content="qualquer coisa aleatória")
        result = classifier_node(expense_state)
        assert result.intent == "unknown"


# ─────────────────────────────────────────
# TESTES: EXTRACTOR NODE
# ─────────────────────────────────────────

class TestExtractorNode:

    @patch("app.agent.nodes.llm")
    def test_extrai_gasto_corretamente(self, mock_llm, expense_state):
        expense_state.intent = "expense"
        mock_llm.invoke.return_value = MagicMock(
            content='{"amount": 45.0, "category": "Alimentação", "description": "ifood"}'
        )
        result = extractor_node(expense_state)
        assert result.amount == 45.0
        assert result.category == "Alimentação"
        assert result.description == "ifood"
        assert result.transaction_type == TransactionType.EXPENSE

    @patch("app.agent.nodes.llm")
    def test_extrai_entrada_corretamente(self, mock_llm, income_state):
        income_state.intent = "income"
        mock_llm.invoke.return_value = MagicMock(
            content='{"amount": 3200.0, "category": "Salário", "description": "salário"}'
        )
        result = extractor_node(income_state)
        assert result.amount == 3200.0
        assert result.category == "Salário"
        assert result.transaction_type == TransactionType.INCOME

    @patch("app.agent.nodes.llm")
    def test_fallback_quando_json_invalido(self, mock_llm, expense_state):
        """Se o LLM retornar JSON inválido, deve preservar valor parseado quando possível."""
        expense_state.intent = "expense"
        mock_llm.invoke.return_value = MagicMock(content="isso não é um json")
        result = extractor_node(expense_state)
        assert result.amount == 45.0
        assert result.category == "Outros"

    @patch("app.agent.nodes.llm")
    def test_remove_markdown_do_json(self, mock_llm, expense_state):
        """Deve conseguir parsear JSON mesmo com blocos markdown."""
        expense_state.intent = "expense"
        mock_llm.invoke.return_value = MagicMock(
            content='```json\n{"amount": 45.0, "category": "Alimentação", "description": "ifood"}\n```'
        )
        result = extractor_node(expense_state)
        assert result.amount == 45.0
        assert result.category == "Alimentação"


# ─────────────────────────────────────────
# TESTES: SAVER NODE
# ─────────────────────────────────────────

class TestSaverNode:

    @patch("app.agent.nodes.save_transaction")
    def test_salva_gasto_e_gera_resposta(self, mock_save):
        state = AgentState(
            phone="5541999999999",
            message="gastei 45 no ifood",
            intent="expense",
            amount=45.0,
            category="Alimentação",
            description="ifood",
            transaction_type=TransactionType.EXPENSE,
        )
        result = saver_node(state)
        mock_save.assert_called_once()
        assert result.response == (
            "Gasto registrado\n\n"
            "Categoria: Alimentação\n"
            "Valor: R$ 45,00\n"
            "Descrição: ifood"
        )

    @patch("app.agent.nodes.save_transaction")
    def test_salva_entrada_e_gera_resposta(self, mock_save):
        state = AgentState(
            phone="5541999999999",
            message="recebi 3200 de salário",
            intent="income",
            amount=3200.0,
            category="Salário",
            description="salário",
            transaction_type=TransactionType.INCOME,
        )
        result = saver_node(state)
        mock_save.assert_called_once()
        assert result.response == (
            "Entrada registrada\n\n"
            "Categoria: Salário\n"
            "Valor: R$ 3.200,00\n"
            "Descrição: salário"
        )


class TestBudgetUpdateNode:

    @patch("app.agent.nodes.update_user_budget")
    @patch("app.agent.nodes.save_transaction")
    def test_atualiza_orcamento_sem_criar_entrada(self, mock_save, mock_update):
        state = AgentState(phone="5541999999999", message="alterar orçamento para 5000")

        result = budget_update_node(state)

        mock_update.assert_called_once_with("5541999999999", 5000.0, complete_onboarding=False)
        mock_save.assert_not_called()
        assert result.response == "Orçamento atualizado\n\nNovo orçamento mensal: R$ 5.000,00"

    @patch("app.agent.nodes.update_user_budget")
    def test_orcamento_invalido(self, mock_update):
        state = AgentState(phone="5541999999999", message="alterar orçamento")

        result = budget_update_node(state)

        mock_update.assert_not_called()
        assert "Não entendi esse valor" in result.response


class TestDuplicateIncomeFlow:

    @patch("app.agent.nodes.create_pending_confirmation")
    @patch("app.agent.nodes.find_possible_duplicate_income")
    def test_detecta_salario_duplicado_e_nao_salva(self, mock_find, mock_create):
        mock_find.return_value = MagicMock(amount=4041.14)
        state = AgentState(
            phone="5541999999999",
            message="recebi 4041,14 de salário",
            intent="income",
            amount=4041.14,
            category="Salário",
            description="salário",
            transaction_type=TransactionType.INCOME,
        )

        result = duplicate_income_check_node(state)

        mock_create.assert_called_once()
        assert "Você já registrou uma entrada de Salário de R$ 4.041,14 neste mês." in result.response
        assert "sim" in result.response

    @patch("app.agent.nodes.get_active_pending_confirmation")
    @patch("app.agent.nodes.resolve_pending_confirmation")
    @patch("app.agent.nodes.save_transaction")
    def test_confirma_pendencia_afirmativa(self, mock_save, mock_resolve, mock_get):
        pending = MagicMock()
        pending.id = 10
        pending.payload_json = json.dumps({
            "transaction_type": "income",
            "amount": 4041.14,
            "category": "Salário",
            "description": "salário",
        })
        mock_get.return_value = pending

        result = pending_confirmation_node(AgentState(phone="5541999999999", message="sim"))

        mock_save.assert_called_once()
        mock_resolve.assert_called_once_with(10, "resolved")
        assert result.response.startswith("Entrada registrada")

    @patch("app.agent.nodes.get_active_pending_confirmation")
    @patch("app.agent.nodes.resolve_pending_confirmation")
    def test_cancela_pendencia_negativa(self, mock_resolve, mock_get):
        pending = MagicMock()
        pending.id = 11
        mock_get.return_value = pending

        result = pending_confirmation_node(AgentState(phone="5541999999999", message="não"))

        mock_resolve.assert_called_once_with(11, "cancelled")
        assert result.response == "Registro cancelado."


class TestQueryNode:

    @patch("app.agent.nodes.get_transactions")
    @patch("app.agent.nodes.get_summary_for_period")
    @patch("app.agent.nodes.get_user")
    def test_resumo_separa_orcamento_entradas_gastos_saldo(self, mock_user, mock_summary, mock_transactions):
        mock_user.return_value = MagicMock(monthly_budget=4641.14)
        mock_summary.return_value = {
            "total_income": 4641.14,
            "total_expense": 820.0,
            "balance": 3821.14,
            "expenses_by_category": {"Alimentação": 820.0},
            "transactions_count": 2,
        }
        mock_transactions.return_value = []

        result = query_node(AgentState(phone="5541999999999", message="resumo do mês"))

        assert "Orçamento mensal cadastrado: R$ 4.641,14" in result.response
        assert "Entradas: R$ 4.641,14" in result.response
        assert "Gastos: R$ 820,00" in result.response
        assert "Saldo: R$ 3.821,14" in result.response
        assert "Orçamento restante: R$ 3.821,14" in result.response

    @patch("app.agent.nodes.get_transactions")
    @patch("app.agent.nodes.get_summary_for_period")
    @patch("app.agent.nodes.get_user")
    def test_extrato_lista_entradas_e_gastos(self, mock_user, mock_summary, mock_transactions):
        mock_user.return_value = MagicMock(monthly_budget=1000)
        mock_summary.return_value = {
            "total_income": 1000,
            "total_expense": 45,
            "balance": 955,
            "expenses_by_category": {},
            "transactions_count": 2,
        }
        income = MagicMock(
            amount=1000,
            category="Salário",
            description="salário",
            created_at=datetime(2026, 7, 1),
        )
        expense = MagicMock(
            amount=45,
            category="Alimentação",
            description="iFood",
            created_at=datetime(2026, 7, 3),
        )
        mock_transactions.side_effect = [[income], [expense]]

        result = query_node(AgentState(phone="5541999999999", message="extrato deste mês"))

        assert "Entradas:" in result.response
        assert "Gastos:" in result.response
        assert "01/07 - salário - R$ 1.000,00" in result.response
        assert "03/07 - Alimentação - R$ 45,00 - iFood" in result.response
        assert "Orçamento restante: R$ 955,00" in result.response


# ─────────────────────────────────────────
# TESTES: FALLBACK NODE
# ─────────────────────────────────────────

class TestFallbackNode:

    def test_retorna_mensagem_de_ajuda(self, unknown_state):
        result = fallback_node(unknown_state)
        assert result.response is not None
        assert "Comandos úteis" in result.response
        assert "gastei" in result.response
        assert "recebi" in result.response
        assert "extrato" in result.response


class TestFinanceAgentGraphIntegration:

    @pytest.mark.asyncio
    @patch("app.agent.nodes.llm")
    async def test_budget_update_through_graph_updates_user_without_income(self, mock_llm, monkeypatch):
        _setup_in_memory_db(monkeypatch)
        _create_ready_user()
        mock_llm.invoke.return_value = MagicMock(content="update_budget")
        agent = FinanceAgent()

        response = await agent.process("5541999999999", "alterar orçamento para 5000")

        user = database.get_user("5541999999999")
        transactions = database.get_transactions("5541999999999")
        assert response == "Orçamento atualizado\n\nNovo orçamento mensal: R$ 5.000,00"
        assert user.monthly_budget == 5000
        assert transactions == []

    @pytest.mark.asyncio
    @patch("app.agent.nodes.llm")
    async def test_duplicate_salary_prompt_and_confirmation_through_graph(self, mock_llm, monkeypatch):
        _setup_in_memory_db(monkeypatch)
        _create_ready_user()
        database.save_transaction(
            phone="5541999999999",
            type=TransactionType.INCOME,
            amount=4041.14,
            category="Salário",
            description="salário",
        )
        mock_llm.invoke.side_effect = [
            MagicMock(content="income"),
            MagicMock(content='{"amount": 4041.14, "category": "Salário", "description": "salário"}'),
        ]
        agent = FinanceAgent()

        prompt = await agent.process("5541999999999", "recebi 4041,14 de salário")
        after_prompt = database.get_transactions("5541999999999", transaction_type=TransactionType.INCOME)
        confirmation = await agent.process("5541999999999", "sim")
        after_confirmation = database.get_transactions("5541999999999", transaction_type=TransactionType.INCOME)

        assert "Você já registrou uma entrada de Salário de R$ 4.041,14 neste mês." in prompt
        assert len(after_prompt) == 1
        assert confirmation.startswith("Entrada registrada")
        assert len(after_confirmation) == 2
