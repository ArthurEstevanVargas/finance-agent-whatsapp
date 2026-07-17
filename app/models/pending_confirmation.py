from sqlalchemy import Column, DateTime, Integer, String, Text
from datetime import datetime

from app.models.transaction import Base


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
