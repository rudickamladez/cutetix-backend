from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from app.schemas.auth import UserFromDB
from app.database import SessionLocal
from app.services.auth import get_by_username

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def fake_decode_token(token, db: Session = Depends(get_db)):
    # This doesn't provide any security at all
    # Check the next version
    return get_by_username(token, db=db)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    user = fake_decode_token(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: Annotated[UserFromDB, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Disabled user")
    return current_user
