import logging
from langgraph.graph import StateGraph, END

from app.agent.state import AgentState, MessageIntent
from app.agent.nodes import (
    access_check_node,
    onboarding_node,
    pending_confirmation_node,
    classifier_node,
    extractor_node,
    image_extractor_node,
    duplicate_income_check_node,
    budget_update_node,
    monthly_cleanup_node,
    saver_node,
    query_node,
    fallback_node,
)

logger = logging.getLogger(__name__)


def route_access(state: AgentState) -> str:
    """Decide se bloqueia ou segue para o onboarding."""
    if state.response is not None:
        return "end"  # Sem acesso → bloqueia
    return "onboarding"  # Tem acesso → segue


def route_onboarding(state: AgentState) -> str:
    """Decide se continua o onboarding ou segue para o fluxo normal."""
    if state.response is not None:
        return "end"  # Onboarding ainda em andamento → responde e termina
    return "pending_confirmation"  # Onboarding concluído → segue fluxo normal


def route_pending_confirmation(state: AgentState) -> str:
    """Decide se uma confirmação pendente encerrou o fluxo."""
    if state.response is not None:
        return "end"
    return "classifier"


def route(state: AgentState) -> str:
    """Decide qual nó executar após o classificador."""
    if state.intent in [MessageIntent.EXPENSE, "expense", "income"]:
        return "extractor"
    elif state.intent == "query":
        return "query"
    elif state.intent == "update_budget":
        return "budget_update"
    elif state.intent == "cleanup":
        return "monthly_cleanup"
    else:
        return "fallback"


def route_duplicate_check(state: AgentState) -> str:
    """Decide se duplicidade pausou o salvamento."""
    if state.response is not None:
        return "end"
    return "saver"


def build_graph():
    graph = StateGraph(AgentState)

    # Adiciona os nós
    graph.add_node("access_check", access_check_node)
    graph.add_node("onboarding", onboarding_node)
    graph.add_node("pending_confirmation", pending_confirmation_node)
    graph.add_node("classifier", classifier_node)
    graph.add_node("extractor", extractor_node)
    graph.add_node("image_extractor", image_extractor_node)
    graph.add_node("duplicate_income_check", duplicate_income_check_node)
    graph.add_node("budget_update", budget_update_node)
    graph.add_node("monthly_cleanup", monthly_cleanup_node)
    graph.add_node("saver", saver_node)
    graph.add_node("query", query_node)
    graph.add_node("fallback", fallback_node)

    # Define o nó de entrada como access_check
    graph.set_entry_point("access_check")

    # Após access_check → bloqueia ou segue
    graph.add_conditional_edges(
        "access_check",
        route_access,
        {
            "end": END,
            "onboarding": "onboarding",
        }
    )

    # Após onboarding → decide se termina ou segue
    graph.add_conditional_edges(
        "onboarding",
        route_onboarding,
        {
            "end": END,
            "pending_confirmation": "pending_confirmation",
        }
    )

    graph.add_conditional_edges(
        "pending_confirmation",
        route_pending_confirmation,
        {
            "end": END,
            "classifier": "classifier",
        }
    )

    # Roteamento condicional após o classificador
    graph.add_conditional_edges(
        "classifier",
        route,
        {
            "extractor": "extractor",
            "query": "query",
            "budget_update": "budget_update",
            "monthly_cleanup": "monthly_cleanup",
            "fallback": "fallback",
        }
    )

    # Após extrator de texto → checa duplicidade antes de salvar
    graph.add_edge("extractor", "duplicate_income_check")

    graph.add_conditional_edges(
        "duplicate_income_check",
        route_duplicate_check,
        {
            "end": END,
            "saver": "saver",
        }
    )

    # Após extrator de imagem → salva no banco
    graph.add_edge("image_extractor", "saver")

    # Nós finais → END
    graph.add_edge("saver", END)
    graph.add_edge("query", END)
    graph.add_edge("budget_update", END)
    graph.add_edge("monthly_cleanup", END)
    graph.add_edge("fallback", END)

    return graph.compile()


class FinanceAgent:
    def __init__(self):
        self.graph = build_graph()
        logger.info("🧠 FinanceAgent inicializado!")

    async def process(self, phone: str, message: str) -> str:
        """Processa uma mensagem de texto e retorna a resposta."""
        logger.info(f"📩 Processando mensagem de {phone}: {message}")

        initial_state = AgentState(phone=phone, message=message)
        final_state = self.graph.invoke(initial_state)

        return final_state["response"]

    async def process_image(self, phone: str, image_url: str, caption: str = "") -> str:
        """Processa uma imagem e retorna a resposta."""
        logger.info(f"🖼️ Processando imagem de {phone}: {image_url}")

        # Verifica acesso e onboarding antes de processar a imagem
        initial_state = AgentState(
            phone=phone,
            message=caption or "comprovante",
            image_url=image_url,
        )

        access_result = access_check_node(initial_state)
        if access_result.response is not None:
            return access_result.response

        onboarding_result = onboarding_node(access_result)
        if onboarding_result.response is not None:
            return onboarding_result.response

        # Processa imagem normalmente
        state_after_extractor = image_extractor_node(onboarding_result)
        state_after_saver = saver_node(state_after_extractor)

        return state_after_saver.response
