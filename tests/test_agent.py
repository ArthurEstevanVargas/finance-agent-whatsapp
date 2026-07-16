import pytest
from unittest.mock import patch, MagicMock
from app.agent.nodes import classifier_node, extractor_node, saver_node, fallback_node
from app.agent.state import AgentState
from app.models.transaction import TransactionType


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
        """Se o LLM retornar JSON inválido, deve usar valores padrão."""
        expense_state.intent = "expense"
        mock_llm.invoke.return_value = MagicMock(content="isso não é um json")
        result = extractor_node(expense_state)
        assert result.amount == 0.0
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
        assert "Gasto registrado" in result.response
        assert "R$ 45,00" in result.response
        assert "Alimentação" in result.response

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
        assert "Entrada registrado" in result.response
        assert "R$ 3.200,00" in result.response


# ─────────────────────────────────────────
# TESTES: FALLBACK NODE
# ─────────────────────────────────────────

class TestFallbackNode:

    def test_retorna_mensagem_de_ajuda(self, unknown_state):
        result = fallback_node(unknown_state)
        assert result.response is not None
        assert "Não entendi" in result.response
        assert "gastei" in result.response
        assert "recebi" in result.response
