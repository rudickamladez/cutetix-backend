from pydantic_settings import BaseSettings


# https://fastapi.tiangolo.com/advanced/settings
class Settings(BaseSettings):
    sqlalchemy_database_url: str
    cors_origins: list[str]
    jwt_secret_location: str
    jwt_public_location: str
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 30

    @property
    def jwt_secret(self):
        with open(self.jwt_secret_location, "r") as f:
            return f.read()

    @property
    def jwt_public(self):
        with open(self.jwt_public_location, "r") as f:
            return f.read()

    smtp_from: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str


settings = Settings()
