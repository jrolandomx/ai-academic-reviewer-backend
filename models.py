from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="reviewer")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    review_type = Column(String)
    review_content = Column(Text)
    score = Column(Integer)
    ai_probability = Column(String)
    badge = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
