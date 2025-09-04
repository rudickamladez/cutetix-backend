from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user
from app.schemas.auth import AuthTokenResponse, UserFromDB, UserLogin, UserRegister
from app.database import SessionLocal
import app.services.auth as auth_service

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={404: {"description": "Not found"}},
)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", response_model=UserFromDB)
def register(user: UserLogin, db: Session = Depends(get_db)):
    return auth_service.register(UserRegister.model_validate(user.model_dump()), db=db)


@router.post("/token", response_model=AuthTokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                db: Session = Depends(get_db)):
    return auth_service.login(form_data.username, form_data.password, db=db)


@router.get("/users/me", response_model=UserFromDB)
async def read_users_me(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
):
    return current_user
