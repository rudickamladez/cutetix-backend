"""Main module of Cute Tickets project"""
from datetime import datetime
import sys
from app.features.git import Git
from app.routers import events, ticket_groups, tickets, auth, users
from app.schemas.root import RootResponse
from app.middleware import auth as auth_middleware
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi_mcp import AuthConfig, FastApiMCP
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.schemas.settings import settings
import app.models  # Important for table registrations
from app.database import engine, BaseModelMixin


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health-check" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup block
    BaseModelMixin.metadata.create_all(bind=engine)

    yield
    # shutdown block

app = FastAPI(
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "persistAuthorization": True,
        "tryItOutEnabled": True,
    },
    title="CuteTix – Cute Tickets Information System",
    description="REST API with database of ticket reservations",
    lifespan=lifespan
)

origins = settings.cors_origins
if origins is None:
    print(
        'Missing defined ENV variable CORS_ORIGINS, using default value ["*"].',
        file=sys.stderr,
    )
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=RootResponse)
@app.head("/", response_model=RootResponse, include_in_schema=False)
async def root():
    """Root path method"""
    git = Git()
    return {
        "git": git.short_hash(),
        "message": "Hello World",
        "time": datetime.now(),
    }


@app.get("/health-check", response_model=str, include_in_schema=False)
def health_check():
    """Method for docker container health check"""
    return "success"


app.include_router(auth.router)
app.include_router(events.router)
app.include_router(ticket_groups.router)
app.include_router(tickets.router)
app.include_router(users.router)

mcp_oauth_enabled = settings.mcp_oauth_enabled or (
    settings.mcp_public_base_url
    and settings.mcp_oauth_issuer
    and settings.mcp_oauth_authorization_endpoint
    and settings.mcp_oauth_token_endpoint
)

if settings.mcp_oauth_enabled and not mcp_oauth_enabled:
    raise ValueError(
        "MCP OAuth is enabled, but required settings are missing. "
        "Set MCP_PUBLIC_BASE_URL, MCP_OAUTH_ISSUER, MCP_OAUTH_AUTHORIZATION_ENDPOINT, "
        "and MCP_OAUTH_TOKEN_ENDPOINT."
    )

auth_config = AuthConfig(
    dependencies=[Depends(auth_middleware.mcp_authentication)],
)

if mcp_oauth_enabled:
    scopes_supported = settings.mcp_oauth_scopes_supported or list(
        auth_middleware.OAUTH_SCOPES.keys()
    )
    custom_oauth_metadata = {
        "issuer": settings.mcp_oauth_issuer,
        "authorization_endpoint": settings.mcp_oauth_authorization_endpoint,
        "token_endpoint": settings.mcp_oauth_token_endpoint,
        "scopes_supported": scopes_supported,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": settings.mcp_oauth_token_endpoint_auth_methods_supported,
        "code_challenge_methods_supported": settings.mcp_oauth_code_challenge_methods_supported,
    }
    if settings.mcp_oauth_registration_endpoint:
        custom_oauth_metadata["registration_endpoint"] = settings.mcp_oauth_registration_endpoint
    auth_config = AuthConfig(
        dependencies=[Depends(auth_middleware.mcp_authentication)],
        custom_oauth_metadata=custom_oauth_metadata,
    )

    @app.get(
        settings.mcp_oauth_resource_metadata_path,
        include_in_schema=False,
        operation_id="oauth_protected_resource_metadata",
    )
    async def oauth_protected_resource_metadata():
        if not settings.mcp_public_base_url or not settings.mcp_oauth_issuer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OAuth not configured")
        base_url = settings.mcp_public_base_url.rstrip("/")
        resource_metadata = {
            "resource": base_url,
            "authorization_servers": [settings.mcp_oauth_issuer],
            "scopes_supported": scopes_supported,
        }
        if settings.mcp_oauth_resource_documentation:
            resource_metadata["resource_documentation"] = settings.mcp_oauth_resource_documentation
        return resource_metadata

mcp = FastApiMCP(
    app,
    auth_config=auth_config,
)

# Mount the MCP server directly to your FastAPI app
mcp.mount_http()
