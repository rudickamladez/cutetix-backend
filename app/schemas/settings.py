from pydantic_settings import BaseSettings


# https://fastapi.tiangolo.com/advanced/settings
class Settings(BaseSettings):
    sqlalchemy_database_url: str
    cors_origins: list[str]
    jwt_secret_location: str
    jwt_public_location: str
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 30  # half hour
    refresh_token_expire_minutes: int = 60 * 24 * 7  # one week
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "CuteTix"
    webauthn_origin: str = "http://localhost"
    webauthn_require_user_verification: bool = True
    webauthn_challenge_ttl_seconds: int = 300

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
