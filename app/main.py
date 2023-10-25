from fastapi import FastAPI
from datetime import datetime
from .features.git import Git

app = FastAPI(
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "persistAuthorization": True,
        "tryItOutEnabled": True
    },
    title="CuteTix – Cute Tickets Information System",
    description="REST API with database of ticket reservations"
)


@app.get("/")
async def root():
    git = Git()
    return {
        "git": git.short_hash(),
        "message": "Hello World",
        "time": datetime.utcnow()
    }
