"""Main module of Cute Tickets project"""
from datetime import datetime
import sys
from app.features.git import Git
from app.routers import events, ticket_groups, tickets, auth, users
from app.schemas.root import RootResponse
from app.middleware import auth as auth_middleware
from fastapi import Depends, FastAPI
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

mcp = FastApiMCP(
    app,
    auth_config=AuthConfig(
        dependencies=[Depends(auth_middleware.oauth2_scheme)],
    ),
)

# Mount the MCP server directly to your FastAPI app
mcp.mount_http()
