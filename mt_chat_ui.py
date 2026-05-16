"""
MT Chat UI - Real end-to-end test of MemoryThread
FastAPI backend + HTML/JS frontend

Run:
    python mt_chat_ui.py

Then open: http://localhost:7860
"""

import os
import json
import time
import threading
import httpx
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ── MT SDK ──────────────────────────────────────────────────────────────────
from memory_thread.sdk import MemoryClient
from memory_thread.services.tms_service import TruthVectorService

# Warm up the MemoryClient once at startup (use_db=True → Postgres + Qdrant)
print("[MT] Initialising MemoryThread (Postgres + Qdrant)...")
_mt = MemoryClient(namespace="mt_chat", use_db=True)
print(f"[MT] Ready — DB:{getattr(_mt, '_db_type', '?')}  Qdrant:{_mt._qdrant is not None}")

# Pre-warm the embedding model NOW so first query is instant
print("[MT] Pre-warming embedding model...")
from memory_thread.utils.embeddings import generate_embeddings

generate_embeddings(("warmup",))
print("[MT] Embedding model ready.")


# ── OpenRouter client ────────────────────────────────────────────────────────
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free model fallback chain — user's actual available free models on OpenRouter
FREE_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-120b:free",
    "minimax/minimax-m2.5:free",
    "arcee-ai/trinity-large-preview:free",
]
# If user set a specific model in .env, try it first
if OR_MODEL and OR_MODEL not in FREE_MODELS:
    FREE_MODELS.insert(0, OR_MODEL)

# Models that reject system role — merge system prompt into user message instead
NO_SYSTEM_MODELS = {"google/gemma", "google/gemma-3"}


def _adapt_messages(model: str, messages: list) -> list:
    """Some models don't support system role — merge into user message."""
    if any(model.startswith(prefix) for prefix in NO_SYSTEM_MODELS):
        adapted = []
        sys_content = ""
        for m in messages:
            if m["role"] == "system":
                sys_content = m["content"]
            else:
                adapted.append(m)
        if sys_content and adapted:
            adapted[0] = {
                "role": adapted[0]["role"],
                "content": f"{sys_content}\n\n{adapted[0]['content']}",
            }
        return adapted
    return messages


def call_openrouter(messages: list):
    headers = {
        "Authorization": f"Bearer {OR_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:7860",
        "X-Title": "MemoryThread Chat",
    }
    seen = set()
    for model in FREE_MODELS:
        if model in seen:
            continue
        seen.add(model)
        payload = {"model": model, "messages": _adapt_messages(model, messages)}
        r = httpx.post(OR_URL, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            data = r.json()
            data["_model_used"] = model
            print(f"[OR] Using: {model}")
            return data
        # 429 = rate limited, try next; 400/404 = model issue, try next
        print(f"[OR] {model} -> {r.status_code}: {r.text[:160]}")
    raise RuntimeError(f"All OpenRouter models failed. Check API key and model availability.")


# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="MT Chat UI")
import os

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MT_ALLOWED_ORIGINS", "").split(",")
    if os.environ.get("MT_ALLOWED_ORIGINS")
    else ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Pydantic models ──────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    namespace: Optional[str] = "mt_chat"


class RecallRequest(BaseModel):
    query: str
    top_k: int = 8


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(open(Path(__file__).parent / "mt_chat_ui.html", encoding="utf-8").read())


@app.post("/api/chat")
async def chat(req: ChatRequest):
    mt = _mt  # shared client

    # 1. Store the user message in MT
    eid = mt.remember(
        content=req.message,
        source="user",
        confidence=0.95,
        memory_type="event",
    )

    # 2. Pull relevant MT context for this query
    context_str = mt.get_context_for_llm(req.message, max_tokens=600)

    # 3. Build the LLM prompt
    system_prompt = f"""You are an AI assistant with a persistent memory system called MemoryThread.
Below are the most relevant memories retrieved for this conversation.
Use them to answer thoughtfully. If memories are irrelevant, ignore them.

--- MEMORY CONTEXT ---
{context_str}
--- END CONTEXT ---

Always be honest. If you're using a memory to answer, say so naturally."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.message},
    ]

    # 4. Call OpenRouter
    try:
        resp = call_openrouter(messages)
        answer = resp["choices"][0]["message"]["content"]
        model_used = resp.get("_model_used", resp.get("model", OR_MODEL))
    except Exception as e:
        answer = f"[LLM error: {e}]"
        model_used = OR_MODEL

    # 5. Store assistant reply in MT
    mt.remember(
        content=f"Assistant replied: {answer[:200]}",
        source="agent",
        confidence=0.85,
        memory_type="event",
    )

    # 6. Gather debug payload
    recall_result = mt.recall(req.message, top_k=5)
    stats = mt.get_stats()

    memories_payload = []
    for m in recall_result.memories:
        memories_payload.append(
            {
                "content": m.content,
                "truth_score": round(m.truth_score, 3),
                "confidence": round(m.confidence, 3),
                "authority": round(m.authority, 3),
                "freshness": round(m.freshness, 3),
                "source": m.source,
                "memory_type": m.memory_type,
            }
        )

    return JSONResponse(
        {
            "answer": answer,
            "model": model_used,
            "context_used": context_str,
            "memories": memories_payload,
            "stats": {
                "total_memories": stats.get("total_memories", 0),
                "total_events": stats.get("total_events", 0),
                "avg_truth_score": round(stats.get("avg_truth_score", 0), 3),
                "namespace": stats.get("namespace", "?"),
                "db_type": stats.get("db_type", "?"),
                "qdrant_connected": stats.get("qdrant_connected", False),
            },
            "entity_id": str(eid),
        }
    )


@app.post("/api/recall")
async def recall(req: RecallRequest):
    result = _mt.recall(req.query, top_k=req.top_k)
    return JSONResponse(
        {
            "query": result.query,
            "total_found": result.total_found,
            "memories": [
                {
                    "content": m.content,
                    "truth_score": round(m.truth_score, 3),
                    "confidence": round(m.confidence, 3),
                    "authority": round(m.authority, 3),
                    "freshness": round(m.freshness, 3),
                    "source": m.source,
                    "memory_type": m.memory_type,
                }
                for m in result.memories
            ],
        }
    )


@app.get("/api/stats")
async def stats():
    s = _mt.get_stats()
    return JSONResponse(s)


@app.post("/api/clear")
async def clear():
    _mt.clear()
    return JSONResponse({"status": "cleared"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="warning")
