from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
)

from datetime import datetime

from database import Base


class Review(Base):
    __tablename__ = "reviews"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    filename = Column(String)

    review_type = Column(String)

    badge = Column(String)

    score = Column(String)

    review = Column(Text)

    ai_probability = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    username = Column(
        String,
        unique=True,
    )

    password = Column(String)