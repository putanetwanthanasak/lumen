from fastapi import FastAPI

app = FastAPI(title="Lumen")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}
