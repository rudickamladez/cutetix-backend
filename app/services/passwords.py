from passlib.context import CryptContext


# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    bcrypt__rounds=12,
    deprecated="auto",
)


def verify_password(plaintext_password, hashed_password):
    return pwd_context.verify(plaintext_password, hashed_password)

    # pokud bylo původně bcrypt -> rehash na argon2
    # if ok and pwd_context.identify(hashed_password) == "bcrypt":
    #     new_hash = pwd_context.hash(plaintext_password)
    #     # TODO: update it in the DB


def get_password_hash(password):
    return pwd_context.hash(password)
