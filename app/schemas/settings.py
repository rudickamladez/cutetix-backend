from pydantic_settings import BaseSettings


# https://fastapi.tiangolo.com/advanced/settings
class Settings(BaseSettings):
    sqlalchemy_database_url: str
    cors_origins: list[str]
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    smtp_from: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str


settings = Settings()
