from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.transaction import Base, Transaction, TransactionType
from app.services import database


def _setup_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def _insert_transaction(session_factory, phone, type_, amount, category, description, created_at):
    with session_factory() as session:
        tx = Transaction(
            phone=phone,
            type=type_,
            amount=amount,
            category=category,
            description=description,
            created_at=created_at,
        )
        session.add(tx)
        session.commit()


def test_get_summary_for_period_separates_income_expense_and_balance(monkeypatch):
    session_factory = _setup_db(monkeypatch)
    _insert_transaction(session_factory, "1", TransactionType.INCOME, 4641.14, "Salário", "salário", datetime(2026, 7, 1))
    _insert_transaction(session_factory, "1", TransactionType.EXPENSE, 820, "Alimentação", "mercado", datetime(2026, 7, 3))
    _insert_transaction(session_factory, "1", TransactionType.EXPENSE, 10, "Transporte", "uber", datetime(2026, 6, 30))

    summary = database.get_summary_for_period("1", datetime(2026, 7, 1), datetime(2026, 8, 1))

    assert summary["total_income"] == 4641.14
    assert summary["total_expense"] == 820
    assert summary["balance"] == 3821.14
    assert summary["expenses_by_category"] == {"Alimentação": 820}


def test_get_transactions_filters_by_type_category_and_text(monkeypatch):
    session_factory = _setup_db(monkeypatch)
    _insert_transaction(session_factory, "1", TransactionType.INCOME, 3000, "Salário", "salário", datetime(2026, 7, 1))
    _insert_transaction(session_factory, "1", TransactionType.EXPENSE, 45, "Alimentação", "ifood", datetime(2026, 7, 2))
    _insert_transaction(session_factory, "2", TransactionType.EXPENSE, 99, "Alimentação", "ifood", datetime(2026, 7, 2))

    incomes = database.get_transactions("1", transaction_type=TransactionType.INCOME)
    food = database.get_transactions("1", category="alimentação")
    salary = database.get_transactions("1", text_filter="salário")

    assert len(incomes) == 1
    assert incomes[0].type == TransactionType.INCOME
    assert len(food) == 1
    assert food[0].amount == 45
    assert len(salary) == 1
    assert salary[0].category == "Salário"


def test_find_possible_duplicate_income_same_month(monkeypatch):
    session_factory = _setup_db(monkeypatch)
    _insert_transaction(session_factory, "1", TransactionType.INCOME, 4041.14, "Salário", "salário", datetime(2026, 7, 1))

    duplicate = database.find_possible_duplicate_income(
        "1",
        4041.14,
        datetime(2026, 7, 1),
        datetime(2026, 8, 1),
        "Salário",
        "salário",
    )

    assert duplicate is not None
    assert duplicate.amount == 4041.14


def test_pending_confirmation_lifecycle(monkeypatch):
    _setup_db(monkeypatch)

    pending = database.create_pending_confirmation(
        phone="1",
        action_type="duplicate_income",
        payload={"amount": 100},
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )

    active = database.get_active_pending_confirmation("1", "duplicate_income")
    assert active is not None
    assert active.id == pending.id

    database.resolve_pending_confirmation(pending.id, "resolved")
    assert database.get_active_pending_confirmation("1", "duplicate_income") is None


def test_expired_pending_confirmation_is_not_active(monkeypatch):
    _setup_db(monkeypatch)
    database.create_pending_confirmation(
        phone="1",
        action_type="duplicate_income",
        payload={"amount": 100},
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    )

    assert database.get_active_pending_confirmation("1", "duplicate_income") is None
