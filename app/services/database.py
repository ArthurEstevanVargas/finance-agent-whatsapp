from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json
import os

from app.models.transaction import Base, Transaction, TransactionType
from app.models.user import User, OnboardingStep, PlanStatus
from app.models.pending_confirmation import PendingConfirmation

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finza.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Cria as tabelas no banco se não existirem."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Retorna uma sessão do banco."""
    return SessionLocal()


# ─────────────────────────────────────────
# FUNÇÕES DE USUÁRIO
# ─────────────────────────────────────────

def get_user(phone: str) -> User | None:
    """Busca um usuário pelo telefone."""
    with get_session() as session:
        user = session.query(User).filter(User.phone == phone).first()
        if user:
            session.expunge(user)
        return user


def create_user(phone: str) -> User:
    """Cria um novo usuário."""
    with get_session() as session:
        user = User(
            phone=phone,
            onboarding_step=OnboardingStep.WAITING_NAME,
            plan_status=PlanStatus.TRIAL,
            trial_start=datetime.utcnow(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def update_user_name(phone: str, name: str) -> User:
    """Atualiza o nome do usuário e avança o onboarding."""
    with get_session() as session:
        user = session.query(User).filter(User.phone == phone).first()
        user.name = name
        user.onboarding_step = OnboardingStep.WAITING_BUDGET
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def update_user_budget(phone: str, budget: float, complete_onboarding: bool = True) -> User:
    """Atualiza o orçamento do usuário e finaliza o onboarding."""
    with get_session() as session:
        user = session.query(User).filter(User.phone == phone).first()
        user.monthly_budget = budget
        if complete_onboarding:
            user.onboarding_step = OnboardingStep.DONE
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def activate_user_plan(phone: str, plan: str) -> User:
    """Ativa um plano pago para o usuário."""
    plan_durations = {
        "mensal": 30,
        "trimestral": 90,
        "semestral": 180,
    }
    days = plan_durations.get(plan, 30)

    with get_session() as session:
        user = session.query(User).filter(User.phone == phone).first()
        user.plan = plan
        user.plan_status = PlanStatus.ACTIVE
        user.plan_expires_at = datetime.utcnow() + timedelta(days=days)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def expire_user_plan(phone: str) -> User:
    """Marca o plano do usuário como expirado."""
    with get_session() as session:
        user = session.query(User).filter(User.phone == phone).first()
        user.plan_status = PlanStatus.EXPIRED
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


# ─────────────────────────────────────────
# FUNÇÕES DE TRANSAÇÃO
# ─────────────────────────────────────────

def save_transaction(phone: str, type: TransactionType, amount: float, category: str, description: str = None) -> Transaction:
    """Salva uma transação no banco."""
    with get_session() as session:
        transaction = Transaction(
            phone=phone,
            type=type,
            amount=amount,
            category=category,
            description=description,
        )
        session.add(transaction)
        session.commit()
        session.refresh(transaction)
        session.expunge(transaction)
        return transaction


def get_summary(phone: str, days: int = 30) -> dict:
    """Retorna um resumo financeiro dos últimos X dias."""
    since = datetime.utcnow() - timedelta(days=days)

    with get_session() as session:
        transactions = (
            session.query(Transaction)
            .filter(Transaction.phone == phone)
            .filter(Transaction.created_at >= since)
            .all()
        )

        total_income = sum(t.amount for t in transactions if t.type == TransactionType.INCOME)
        total_expense = sum(t.amount for t in transactions if t.type == TransactionType.EXPENSE)
        balance = total_income - total_expense

        expenses_by_category = {}
        for t in transactions:
            if t.type == TransactionType.EXPENSE:
                expenses_by_category[t.category] = expenses_by_category.get(t.category, 0) + t.amount

        return {
            "period_days": days,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": balance,
            "expenses_by_category": expenses_by_category,
            "transactions_count": len(transactions),
        }


def get_recent_transactions(phone: str, limit: int = 5) -> list[Transaction]:
    """Retorna as últimas transações do usuário."""
    with get_session() as session:
        transactions = (
            session.query(Transaction)
            .filter(Transaction.phone == phone)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .all()
        )
        for t in transactions:
            session.expunge(t)
        return transactions
    
def get_transactions_by_category(phone: str, category: str, days: int = 30) -> list[Transaction]:
    """Retorna transações de uma categoria específica."""
    since = datetime.utcnow() - timedelta(days=days)

    with get_session() as session:
        transactions = (
            session.query(Transaction)
            .filter(Transaction.phone == phone)
            .filter(Transaction.created_at >= since)
            .filter(Transaction.category.ilike(f"%{category}%"))
            .order_by(Transaction.created_at.desc())
            .all()
        )
        for t in transactions:
            session.expunge(t)
        return transactions


def get_transactions(
    phone: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    transaction_type: TransactionType | None = None,
    category: str | None = None,
    text_filter: str | None = None,
    limit: int | None = None,
) -> list[Transaction]:
    """Retorna transações filtradas por período, tipo, categoria e texto."""
    with get_session() as session:
        query = session.query(Transaction).filter(Transaction.phone == phone)
        if start_date is not None:
            query = query.filter(Transaction.created_at >= start_date)
        if end_date is not None:
            query = query.filter(Transaction.created_at < end_date)
        if transaction_type is not None:
            query = query.filter(Transaction.type == transaction_type)
        if category:
            query = query.filter(Transaction.category.ilike(f"%{category}%"))
        if text_filter:
            pattern = f"%{text_filter}%"
            query = query.filter(
                Transaction.description.ilike(pattern) | Transaction.category.ilike(pattern)
            )
        query = query.order_by(Transaction.created_at.desc())
        if limit is not None:
            query = query.limit(limit)
        transactions = query.all()
        for t in transactions:
            session.expunge(t)
        return transactions


def get_summary_for_period(phone: str, start_date: datetime, end_date: datetime) -> dict:
    """Retorna resumo financeiro entre start_date e end_date."""
    transactions = get_transactions(phone=phone, start_date=start_date, end_date=end_date)
    total_income = sum(t.amount for t in transactions if t.type == TransactionType.INCOME)
    total_expense = sum(t.amount for t in transactions if t.type == TransactionType.EXPENSE)
    expenses_by_category = {}
    for t in transactions:
        if t.type == TransactionType.EXPENSE:
            expenses_by_category[t.category] = expenses_by_category.get(t.category, 0) + t.amount
    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": round(total_income - total_expense, 2),
        "expenses_by_category": expenses_by_category,
        "transactions_count": len(transactions),
    }


def get_expenses_by_category_for_period(phone: str, start_date: datetime, end_date: datetime) -> dict[str, float]:
    summary = get_summary_for_period(phone, start_date, end_date)
    return summary["expenses_by_category"]


def find_possible_duplicate_income(
    phone: str,
    amount: float,
    start_date: datetime,
    end_date: datetime,
    category: str,
    description: str | None,
) -> Transaction | None:
    """Busca entrada possivelmente duplicada no período."""
    text_filter = "salário" if "sal" in (category or "").lower() else description
    transactions = get_transactions(
        phone=phone,
        start_date=start_date,
        end_date=end_date,
        transaction_type=TransactionType.INCOME,
        text_filter=text_filter,
    )
    for t in transactions:
        if abs(float(t.amount) - float(amount)) < 0.01:
            return t
    return None


def create_pending_confirmation(
    phone: str,
    action_type: str,
    payload: dict,
    expires_at: datetime,
) -> PendingConfirmation:
    """Cria uma confirmação pendente, cancelando pendências anteriores do mesmo tipo."""
    with get_session() as session:
        now = datetime.utcnow()
        session.query(PendingConfirmation).filter(
            PendingConfirmation.phone == phone,
            PendingConfirmation.action_type == action_type,
            PendingConfirmation.status == "pending",
        ).update({"status": "cancelled", "resolved_at": now})
        pending = PendingConfirmation(
            phone=phone,
            action_type=action_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
            status="pending",
            expires_at=expires_at,
        )
        session.add(pending)
        session.commit()
        session.refresh(pending)
        session.expunge(pending)
        return pending


def get_active_pending_confirmation(phone: str, action_type: str | None = None) -> PendingConfirmation | None:
    """Retorna a confirmação pendente ativa do usuário."""
    now = datetime.utcnow()
    with get_session() as session:
        query = session.query(PendingConfirmation).filter(
            PendingConfirmation.phone == phone,
            PendingConfirmation.status == "pending",
            PendingConfirmation.expires_at > now,
        )
        if action_type:
            query = query.filter(PendingConfirmation.action_type == action_type)
        pending = query.order_by(PendingConfirmation.created_at.desc()).first()
        if pending:
            session.expunge(pending)
        return pending


def resolve_pending_confirmation(pending_id: int, status: str) -> None:
    """Marca uma confirmação pendente como resolvida, cancelada ou expirada."""
    with get_session() as session:
        pending = session.query(PendingConfirmation).filter(PendingConfirmation.id == pending_id).first()
        if not pending:
            return
        pending.status = status
        pending.resolved_at = datetime.utcnow()
        session.commit()
