from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from app.features.git import Git
import os
import json
import sys
from app.routers import events
from app.schemas import RootResponse

app = FastAPI(
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "persistAuthorization": True,
        "tryItOutEnabled": True,
    },
    title="CuteTix – Cute Tickets Information System",
    description="REST API with database of ticket reservations",
)

try:
    origins = json.loads(os.getenv("CORS_ORIGINS"))
except:  # noqa: E722
    print(
        'Missing defined ENV variable CORS_ORIGINS, using default value ["*"].',
        file=sys.stderr,
    )
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=RootResponse)
async def root():
    git = Git()
    return {
        "git": git.short_hash(),
        "message": "Hello World",
        "time": datetime.utcnow(),
    }


@app.get("/health-check", response_model=str)
def health_check():
    return "success"


app.include_router(events.router)
