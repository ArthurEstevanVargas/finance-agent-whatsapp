from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.models.transaction import TransactionType


class MessageIntent(str):
    EXPENSE = "expense"       # "gastei 45 no ifood"
    INCOME = "income"         # "recebi salário 3200"
    QUERY = "query"           # "quanto gastei essa semana?"
    UPDATE_BUDGET = "update_budget"  # "alterar orçamento para 5000"
    UNKNOWN = "unknown"       # mensagem não reconhecida


class AgentState(BaseModel):
    # Dados da mensagem recebida
    phone: str
    message: str
    image_url: Optional[str] = None

    # Resultado da classificação
    intent: Optional[str] = None

    # Dados extraídos da mensagem (quando for gasto ou entrada)
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    transaction_type: Optional[TransactionType] = None

    # Resposta final que será enviada ao usuário
    response: Optional[str] = None

    # Metadados opcionais de consulta
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    query_kind: Optional[str] = None
