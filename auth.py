from jose import JWTError, jwt

from passlib.context import CryptContext

from fastapi import (
    HTTPException,
    Depends,
)

from fastapi.security import (
    OAuth2PasswordBearer,
)

from sqlalchemy.orm import Session

from database import SessionLocal

from models import User

import os


SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "SUPER_SECRET_KEY_123",
)

ALGORITHM = "HS256"


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login"
)


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


def hash_password(password: str):
    password = password[:72]

    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
):
    plain_password = plain_password[:72]

    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(data: dict):
    return jwt.encode(
        data,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="No autorizado",
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        username: str = payload.get("sub")

        if username is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if user is None:
        raise credentials_exception

    return user


def admin_required(
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado",
        )

    return current_user