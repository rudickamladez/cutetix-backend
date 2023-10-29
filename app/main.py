from fastapi import FastAPI
from datetime import datetime
from .features.git import Git

app = FastAPI()


@app.get("/")
async def root():
    git = Git()
    return {
        "git": git.short_hash(),
        "message": "Hello World",
        "time": datetime.utcnow()
    }

@app.get("/health-check")
def health_check():
    return "success"
