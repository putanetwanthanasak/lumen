from fastapi import FastAPI

from app.debts.router import router as debts_router
from app.webhooks.router import router as webhooks_router

app = FastAPI(title="Lumen")
app.include_router(webhooks_router)
app.include_router(debts_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}
