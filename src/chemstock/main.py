from fastapi import FastAPI

app = FastAPI(
    title="ChemStock",
    description="Laboratory chemical inventory and safety management API",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
