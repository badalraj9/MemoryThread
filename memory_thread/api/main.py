from fastapi import FastAPI
from memory_thread.api.gateway import router as gateway_router
from memory_thread.api.routers import maintenance

app = FastAPI(title="Memory Thread Engine", version="0.4.0")

app.include_router(gateway_router)
app.include_router(maintenance.router)

@app.get("/")
def health_check():
    return {"status": "active", "version": "0.4.0"}
