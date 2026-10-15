from fastapi import FastAPI

from app.webhooks.router import router as webhooks_router

app = FastAPI(title="Lumen")
app.include_router(webhooks_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}
