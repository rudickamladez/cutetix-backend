from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user
from app.schemas.auth import TokenResponse, UserInDB, UserFromDB, UserRegister
from app.database import SessionLocal
from app.services.auth import fake_hash_password, get_by_username, create

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
def register(user: UserRegister, db: Session = Depends(get_db)):
    user_dict = get_by_username(user.username, db=db)
    if user_dict:
        raise HTTPException(
            status_code=400, detail="Username already registered"
        )
    user.hashed_password = fake_hash_password(user.plaintext_password)
    user.plaintext_password = None
    return create(user, db=db)


@router.post("/token", response_model=TokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                db: Session = Depends(get_db)):
    db_user = get_by_username(form_data.username, db=db)
    if not db_user:
        raise HTTPException(
            status_code=400, detail="Incorrect username"
        )

    if fake_hash_password(form_data.password) != db_user.hashed_password:
        raise HTTPException(
            status_code=400, detail="Incorrect password"
        )

    user = UserInDB.model_validate(db_user, from_attributes=True)

    return {"access_token": user.username, "token_type": "bearer"}


@router.get("/users/me", response_model=UserFromDB)
async def read_users_me(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
):
    return current_user
