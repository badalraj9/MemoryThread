from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any
import asyncio
import time
from memory_thread.nervous.fabric import FabricRouter
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter()

# Global State
fabric_router = FabricRouter(address="ipc://ingest_gateway", mode="ROUTER")
pressure_score = 0.0
producer_registry = {}

class BatchIngestRequest(BaseModel):
    producer_id: str
    events: List[Dict[str, Any]]

class RegisterProducerRequest(BaseModel):
    producer_id: str
    type: str # 'python', 'rust'
    version: str

@router.on_event("startup")
async def startup_event():
    await fabric_router.start()
    asyncio.create_task(pressure_monitor_loop())

@router.on_event("shutdown")
def shutdown_event():
    fabric_router.close()

@router.post("/register")
async def register_producer(req: RegisterProducerRequest):
    producer_registry[req.producer_id] = {
        "type": req.type,
        "version": req.version,
        "connected_at": time.time()
    }
    log.info(f"Registered Producer: {req.producer_id}")
    return {"status": "ok", "throttle": pressure_score}

@router.post("/ingest")
async def ingest_batch(req: BatchIngestRequest):
    # Check Pressure
    if pressure_score > 0.9:
        raise HTTPException(status_code=503, detail="System Overloaded")

    # Forward to Fabric (Mocking ZMQ send for now as Gateway Logic)
    # In real deployment, this pushes to the ZMQ Dealer backend
    # For now, we simulate success
    return {"status": "accepted", "count": len(req.events)}

@router.get("/control/throttle")
async def get_throttle():
    return {"pressure": pressure_score}

async def pressure_monitor_loop():
    """Mock pressure updates based on 'simulated' internal state"""
    global pressure_score
    while True:
        # In real system, query PersistenceScheduler
        # Here we mock it oscillating for testing
        # pressure_score = 0.1
        await asyncio.sleep(1.0)
