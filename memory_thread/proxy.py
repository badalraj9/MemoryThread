"""
MT Proxy — MemoryThread as a drop-in OpenAI-compatible server.

Usage:
    pip install memory-thread
    mt-serve                    # runs on localhost:8000
    mt-serve --backend http://localhost:11434/v1  # Ollama
    mt-serve --backend https://api.openai.com/v1  # OpenAI

Then point your app to http://localhost:8000/v1
Works with LM Studio, Ollama, vLLM, OpenRouter, any OpenAI-compatible API.
Memory injection and guardrails are automatic.
"""

import os
import re
import json
import time
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from memory_thread.sdk import MemoryClient
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.context_monitor import context_monitor
from memory_thread.services.thread_service import thread_service
from memory_thread.services.workflow_induction import workflow_induction
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ── Config ──────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("MT_BACKEND_URL", "http://localhost:11434/v1")
MT_PORT = int(os.environ.get("MT_PORT", "8000"))
MT_AUTO_MEMORY = os.environ.get("MT_AUTO_MEMORY", "true").lower() == "true"
MT_GUARDRAILS = os.environ.get("MT_GUARDRAILS", "true").lower() == "true"
MT_PROXY_POOL_SIZE = int(os.environ.get("MT_PROXY_POOL_SIZE", "10"))

# ── Secret Guardrails ───────────────────────────────────────────
GUARDRAIL_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "[API_KEY_REDACTED]"),
    (r"api[-_]?key[=:]\s*['\"]?[a-zA-Z0-9_-]{16,}", "[API_KEY_REDACTED]"),
    (
        r"-----BEGIN (RSA |EC )?PRIVATE KEY-----.*?-----END (RSA |EC )?PRIVATE KEY-----",
        "[PRIVATE_KEY_REDACTED]",
    ),
    (r"ghp_[a-zA-Z0-9]{36}", "[GITHUB_TOKEN_REDACTED]"),
    (r"hf_[a-zA-Z0-9]{34}", "[HUGGINGFACE_TOKEN_REDACTED]"),
    (r"AKIA[0-9A-Z]{16}", "[AWS_KEY_REDACTED]"),
    (r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_REDACTED]"),
    (r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b", "[SSN_REDACTED]"),
]


def apply_guardrails(text: str) -> str:
    if not MT_GUARDRAILS:
        return text
    for pattern, replacement in GUARDRAIL_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE | re.DOTALL)
    return text


# ── Client Pool ─────────────────────────────────────────────────
class MTProxyPool:
    """Thread-safe pool of MemoryClient instances for concurrent requests."""

    def __init__(self, pool_size: int = MT_PROXY_POOL_SIZE):
        self._pool: asyncio.Queue[MemoryClient] = asyncio.Queue()
        self._thread_registry: Dict[str, str] = {}
        self._registry_lock = asyncio.Lock()
        for _ in range(pool_size):
            self._pool.put_nowait(MemoryClient(namespace="mt_proxy"))

    @asynccontextmanager
    async def get_client(self):
        client = await self._pool.get()
        try:
            yield client
        finally:
            await self._pool.put(client)

    async def get_or_create_thread(self, thread_id: Optional[str] = None) -> str:
        async with self._registry_lock:
            if thread_id and thread_id in self._thread_registry:
                return thread_id
            t = thread_service.create_thread("Chat Session", created_by="user")
            tid = t.thread_id
            if thread_id:
                self._thread_registry[thread_id] = tid
            return tid


proxy_pool = MTProxyPool()

# ── FastAPI App ─────────────────────────────────────────────────
app = FastAPI(title="MemoryThread Proxy", version="1.0.0")
_http = httpx.AsyncClient(timeout=120.0)


# ── Pydantic models ─────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "default"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class MemoryRequest(BaseModel):
    content: str
    source: str = "user"
    confidence: float = 0.9


class RecallRequest(BaseModel):
    query: str
    top_k: int = 5
    mode: str = "graph"


# ── OpenAI-compatible Chat Completions ──────────────────────────
@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    user_msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    if not user_msg:
        return await _proxy_request(req)

    thread_id = await proxy_pool.get_or_create_thread()
    safe_text = apply_guardrails(user_msg)

    if MT_AUTO_MEMORY and safe_text.strip():
        async with proxy_pool.get_client() as mt:
            mt.remember_in_thread(
                content=safe_text, thread_id=thread_id, source="user", confidence=0.95
            )

    context = context_monitor.observe(user_msg, max_tokens=2000)

    modified_messages = []
    if context:
        modified_messages.append({"role": "system", "content": context})
    for m in req.messages:
        modified_messages.append({"role": m.role, "content": m.content})

    backend_req = req.model_dump()
    backend_req["messages"] = modified_messages
    backend_req.pop("stream", None)

    is_stream = req.stream
    if is_stream:
        return StreamingResponse(
            _stream_backend(backend_req, safe_text),
            media_type="text/event-stream",
        )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{BACKEND_URL}/chat/completions",
                json=backend_req,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]

        if MT_AUTO_MEMORY:
            async with proxy_pool.get_client() as mt:
                mt.remember_in_thread(
                    content=f"Assistant: {answer[:300]}",
                    thread_id=thread_id,
                    source="agent",
                    confidence=0.85,
                )

        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


async def _stream_backend(req: Dict, user_text: str):
    thread_id = None
    full_response = ""
    try:
        thread_id = await proxy_pool.get_or_create_thread()
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{BACKEND_URL}/chat/completions", json={**req, "stream": True}
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"
                        if line.strip() != "data: [DONE]":
                            try:
                                data = json.loads(line[6:])
                                delta = data["choices"][0].get("delta", {})
                                full_response += delta.get("content", "")
                            except (json.JSONDecodeError, KeyError, IndexError):
                                pass
                if MT_AUTO_MEMORY and full_response.strip() and thread_id:
                    async with proxy_pool.get_client() as mt:
                        mt.remember_in_thread(
                            content=f"Assistant: {full_response[:300]}",
                            thread_id=thread_id,
                            source="agent",
                            confidence=0.85,
                        )
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    yield "data: [DONE]\n\n"


async def _proxy_request(req: ChatRequest):
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{BACKEND_URL}/chat/completions",
                json=req.model_dump(),
                headers={"Content-Type": "application/json"},
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


# ── Memory Endpoints ────────────────────────────────────────────
@app.post("/v1/memory/remember")
async def remember(req: MemoryRequest):
    async with proxy_pool.get_client() as mt:
        eid = mt.remember(
            content=apply_guardrails(req.content), source=req.source, confidence=req.confidence
        )
    return {"entity_id": str(eid)}


@app.post("/v1/memory/recall")
async def recall(req: RecallRequest):
    async with proxy_pool.get_client() as mt:
        if req.mode == "graph":
            result = mt.recall_graph(req.query, top_k=req.top_k)
        else:
            result = mt.recall(req.query, top_k=req.top_k)
    return {
        "query": result.query,
        "memories": [
            {
                "content": m.content,
                "score": round(m.truth_score, 3),
                "source": m.source,
            }
            for m in result.memories
        ],
    }


@app.post("/v1/memory/golden-thread")
async def golden_thread(entity_id: str):
    from memory_thread.services.golden_thread import golden_thread_service

    eid = uuid.UUID(entity_id) if isinstance(entity_id, str) else entity_id
    result = golden_thread_service.trace(eid)
    return {
        "entity_id": str(eid),
        "events": [
            {
                "sequence": e.sequence,
                "event_type": e.event_type,
                "timestamp": e.timestamp,
                "actor": e.actor,
                "description": e.description,
            }
            for e in result.events
        ],
        "narrative": result.narrative,
        "consistent": result.is_consistent,
    }


@app.get("/v1/threads")
async def list_threads():
    threads = [v["name"] for v in graph_engine.graph.vs if v.attributes().get("type") == "thread"]
    return {"threads": threads}


@app.post("/v1/threads/new")
async def new_thread(title: str = "New Session"):
    t = thread_service.create_thread(title, created_by="user")
    return {"thread_id": t.thread_id, "title": t.title}


@app.post("/v1/agent/observe")
async def agent_observe(text: str):
    context = context_monitor.observe(text, max_tokens=2000)
    return {"injected_context": context, "stats": context_monitor.get_stats()}


# ── Health ──────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "backend": BACKEND_URL,
        "graph_nodes": graph_engine.graph.vcount(),
        "graph_edges": graph_engine.graph.ecount(),
        "guardrails": MT_GUARDRAILS,
        "auto_memory": MT_AUTO_MEMORY,
    }


@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": "memory-thread-proxy", "object": "model"}]}


# ── CLI Entry Point ─────────────────────────────────────────────
def serve():
    import argparse

    parser = argparse.ArgumentParser(description="MemoryThread Proxy")
    parser.add_argument("--backend", default=BACKEND_URL, help="LLM backend URL")
    parser.add_argument("--port", type=int, default=MT_PORT, help="Port to listen on")
    parser.add_argument("--no-memory", action="store_true", help="Disable auto memory")
    parser.add_argument("--no-guardrails", action="store_true", help="Disable secret guardrails")
    args = parser.parse_args()

    global BACKEND_URL, MT_PORT, MT_AUTO_MEMORY, MT_GUARDRAILS
    BACKEND_URL = args.backend
    MT_PORT = args.port
    MT_AUTO_MEMORY = not args.no_memory
    MT_GUARDRAILS = not args.no_guardrails

    print(f"MemoryThread Proxy")
    print(f"   Backend:    {BACKEND_URL}")
    print(f"   Port:       {MT_PORT}")
    print(f"   Pool:       {MT_PROXY_POOL_SIZE} clients")
    print(f"   Auto memory: {MT_AUTO_MEMORY}")
    print(f"   Guardrails:  {MT_GUARDRAILS}")
    print(f"   Point your app to http://localhost:{MT_PORT}/v1")
    print()

    uvicorn.run(app, host="0.0.0.0", port=MT_PORT, log_level="warning")


if __name__ == "__main__":
    serve()
