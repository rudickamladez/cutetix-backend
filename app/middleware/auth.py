from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

fake_users_db = {
    "johndoe": {
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "fakehashedsecret",
        "disabled": False,
    },
    "alice": {
        "uuid": "123e4567-e89b-12d3-a456-426614174001",
        "full_name": "Alice Wonderson",
        "email": "alice@example.com",
        "hashed_password": "fakehashedsecret2",
        "disabled": True,
    },
    "lukas": {
        "uuid": "123e4567-e89b-12d3-a456-426614174002",
        "full_name": "Lukáš Matuška",
        "email": "matuska.lukas@lukasmatuska.cz",
        "hashed_password": "fakehashedlukas",
        "disabled": False,
    },
}


def fake_hash_password(password: str):
    return "fakehashed" + password


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class User(BaseModel):
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    uuid: str
    hashed_password: str
    username: str


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        user_dict["username"] = username
        return UserInDB(**user_dict)


def fake_decode_token(token):
    # This doesn't provide any security at all
    # Check the next version
    user = get_user(fake_users_db, token)
    return user


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    user = fake_decode_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

