from fastapi import APIRouter, HTTPException
from typing import List
from uuid import UUID
from pydantic import BaseModel
from memory_thread.services.identity_service import IdentityService
from memory_thread.models.entity import MergeProposal

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

# In-memory storage for pending proposals (simplification for prototype)
# Real system would store in DB table 'approval_queue'
pending_proposals: List[MergeProposal] = []

@router.get("/proposals")
async def get_proposals():
    # In a real scenario, this would scan or query DB
    # For demo, we trigger a scan and return results
    service = IdentityService()
    # Limit to person for now
    try:
        proposals = service.scan_duplicates("person", threshold=0.85)
        return proposals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/approve/merge")
async def approve_merge(proposal: MergeProposal):
    service = IdentityService()
    try:
        service.execute_merge(proposal)
        return {"status": "merged", "source": proposal.source_entity.id, "target": proposal.target_entity.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health/stats")
async def get_health_stats():
    # Mock dashboard metrics
    return {
        "entities_count": 1000,
        "duplicates_detected": 5,
        "pruning_candidates": 20,
        "average_freshness": 0.88
    }
