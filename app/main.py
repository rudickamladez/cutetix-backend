from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from .features.git import Git
import os
import json
from .routers import events
from .schemas import RootResponse

app = FastAPI(
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "persistAuthorization": True,
        "tryItOutEnabled": True
    },
    title="CuteTix – Cute Tickets Information System",
    description="REST API with database of ticket reservations"
)

origins = json.loads(os.getenv('CORS_ORIGINS'))

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
        "time": datetime.utcnow()
    }


@app.get("/health-check", response_model=str)
def health_check():
    return "success"

app.include_router(events.router)
