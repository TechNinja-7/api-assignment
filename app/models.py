from sqlalchemy import Column, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    message_id = Column(String, primary_key=True, index=True)
    from_msisdn = Column(String, nullable=False, index=True)
    to_msisdn = Column(String, nullable=False)
    ts = Column(String, nullable=False, index=True)
    text = Column(Text, nullable=True)
    created_at = Column(String, nullable=False)
