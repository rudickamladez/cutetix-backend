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
    mcp_public_base_url: str | None = None
    mcp_oauth_enabled: bool = False
    mcp_oauth_internal: bool = False
    mcp_oauth_issuer: str | None = None
    mcp_oauth_authorization_endpoint: str | None = None
    mcp_oauth_token_endpoint: str | None = None
    mcp_oauth_registration_endpoint: str | None = None
    mcp_oauth_client_id: str | None = None
    mcp_oauth_client_secret: str | None = None
    mcp_oauth_scopes_supported: list[str] = []
    mcp_oauth_token_endpoint_auth_methods_supported: list[str] = ["none"]
    mcp_oauth_code_challenge_methods_supported: list[str] = ["S256"]
    mcp_oauth_resource_documentation: str | None = None
    mcp_oauth_resource_metadata_path: str = "/.well-known/oauth-protected-resource"
    mcp_oauth_jwks_url: str | None = None
    mcp_oauth_audience: str | None = None
    mcp_oauth_jwt_algorithms: list[str] = ["RS256"]
    mcp_oauth_username_claims: list[str] = ["preferred_username", "email", "sub"]
    mcp_oauth_redirect_uris: list[str] = []
    mcp_oauth_frontend_login_url: str | None = None

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
