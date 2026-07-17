from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.transaction import Base, TransactionType
from app.services import database


def test_participant_phone_scopes_financial_history(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)

    database.save_transaction(
        phone="5541999999999",
        type=TransactionType.EXPENSE,
        amount=50,
        category="Mercado",
        description="mercado",
    )
    database.save_transaction(
        phone="5541888888888",
        type=TransactionType.EXPENSE,
        amount=80,
        category="Farmacia",
        description="farmacia",
    )

    first_summary = database.get_summary(phone="5541999999999", days=30)
    second_summary = database.get_summary(phone="5541888888888", days=30)

    assert first_summary["total_expense"] == 50
    assert second_summary["total_expense"] == 80


def test_onboarding_uses_participant_phone_not_group_jid(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)

    user = database.create_user("5541999999999")

    assert user.phone == "5541999999999"
    assert not user.phone.endswith("@g.us")
