"""
MT Session — Auto-memory chat session for any LLM.

Wraps any conversation, providing MT operations (remember, recall,
check_contradiction) as LLM-callable tools. The agent decides when
to use memory — no automatic context injection.

Usage:
    python -m memory_thread.session                          # Ollama (default)
    python -m memory_thread.session --provider lm-studio     # LM Studio
    python -m memory_thread.session --provider claude        # Claude API
    python -m memory_thread.session --provider llamacpp      # llama.cpp
"""

import os
import sys
import json
import argparse
import uuid
from typing import Optional

import httpx


# ==============================================================================
# Memory client
# ==============================================================================


_client_cache: dict = {}


def _get_mt(namespace: str = "session"):
    from memory_thread.sdk import MemoryClient

    if namespace not in _client_cache:
        _client_cache[namespace] = MemoryClient(namespace=namespace, use_db=True)
    return _client_cache[namespace]


# ==============================================================================
# MT tools as callable functions (for LLM function calling)
# ==============================================================================

MT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Store information into long-term memory",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "What to remember"},
                    "source": {
                        "type": "string",
                        "enum": ["user", "agent", "system"],
                        "default": "agent",
                    },
                    "confidence": {"type": "number", "default": 0.8},
                    "memory_type": {
                        "type": "string",
                        "enum": ["fact", "event", "preference"],
                        "default": "fact",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search long-term memory for relevant information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_contradiction",
            "description": "Check if a statement contradicts existing memories",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Statement to check"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Get memory system statistics",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


def _execute_tool(name: str, args: dict, namespace: str) -> str:
    mt = _get_mt(namespace)
    if name == "remember":
        eid = mt.remember(
            content=args["content"],
            source=args.get("source", "agent"),
            confidence=args.get("confidence", 0.8),
            memory_type=args.get("memory_type", "fact"),
        )
        return json.dumps({"entity_id": str(eid), "status": "stored"})
    elif name == "recall":
        result = mt.recall(query=args["query"], top_k=args.get("top_k", 5))
        if not result.memories:
            return json.dumps({"memories": [], "total": 0})
        data = [
            {
                "content": m.content,
                "truth_score": m.truth_score,
                "confidence": m.confidence,
                "freshness": m.freshness,
            }
            for m in result.memories
        ]
        return json.dumps({"memories": data, "total": result.total_found})
    elif name == "check_contradiction":
        result = mt.check_contradiction(args["content"])
        return json.dumps(result)
    elif name == "get_stats":
        stats = mt.get_stats()
        return json.dumps(stats)
    return json.dumps({"error": f"unknown tool: {name}"})


# ==============================================================================
# LLM backends
# ==============================================================================


def _call_openai_compatible(
    messages: list, model: str, host: str, system: str, tools: list, timeout: int
) -> dict:
    if system:
        messages = [{"role": "system", "content": system}] + messages
    body = {"model": model, "messages": messages, "temperature": 0.7, "stream": False}
    if tools:
        body["tools"] = tools
    resp = httpx.post(f"{host}/v1/chat/completions", json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _call_claude(
    messages: list, model: str, host: str, system: str, tools: list, timeout: int
) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        return {"error": "Set ANTHROPIC_API_KEY env var"}
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {"model": model or "claude-sonnet-4-20250514", "max_tokens": 4096, "messages": messages}
    if system:
        body["system"] = system
    if tools:
        claude_tools = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                claude_tools.append(
                    {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    }
                )
        body["tools"] = claude_tools
    resp = httpx.post(f"{host}/v1/messages", json=body, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _extract_content_openai(response: dict) -> str:
    choice = response["choices"][0]
    msg = choice["message"]
    if msg.get("tool_calls"):
        return None, msg["tool_calls"]
    return msg.get("content", ""), []


def _extract_content_claude(response: dict) -> tuple:
    if "error" in response:
        return f"[Error: {response['error']}]", []
    for block in response.get("content", []):
        if block["type"] == "text":
            return block["text"], []
        if block["type"] == "tool_use":
            return None, [
                {
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"]),
                    },
                }
            ]
    return "", []


PROVIDERS = {
    "ollama": {
        "host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        "model": os.environ.get("OLLAMA_MODEL", "llama3"),
        "call": _call_openai_compatible,
        "extract": _extract_content_openai,
        "supports_tools": True,
    },
    "lm-studio": {
        "host": os.environ.get("LM_STUDIO_HOST", "http://localhost:1234"),
        "model": os.environ.get("LM_STUDIO_MODEL", ""),
        "call": _call_openai_compatible,
        "extract": _extract_content_openai,
        "supports_tools": False,
    },
    "llamacpp": {
        "host": os.environ.get("LLAMACPP_HOST", "http://localhost:8080"),
        "model": "",
        "call": _call_openai_compatible,
        "extract": _extract_content_openai,
        "supports_tools": False,
    },
    "claude": {
        "host": os.environ.get("CLAUDE_HOST", "https://api.anthropic.com"),
        "model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        "call": _call_claude,
        "extract": _extract_content_claude,
        "supports_tools": True,
    },
}


# ==============================================================================
# Session loop
# ==============================================================================

DEFAULT_SYSTEM = (
    "You are a helpful AI assistant with a long-term memory system. "
    "You have tools to remember and recall information across sessions. "
    "Use them when you need to store something important or look up past context. "
    "Don't use them for every message — only when it's relevant."
)


def run_session(args):
    mt = _get_mt(args.namespace)
    provider = PROVIDERS[args.provider]
    host = args.host or provider["host"]
    model = args.model or provider["model"]
    call_fn = provider["call"]
    extract_fn = provider["extract"]
    system = args.system or DEFAULT_SYSTEM
    tools = MT_TOOLS if provider["supports_tools"] else []
    history: list = []

    print(f"MT Session — {args.provider} ({model or 'default'})", file=sys.stderr)
    print(f"Namespace: {args.namespace}", file=sys.stderr)
    if not provider["supports_tools"]:
        print(
            f"[{args.provider} does not support function calling — MT tools disabled]",
            file=sys.stderr,
        )
    print("Commands: /quit, /forget <id>, /stats", file=sys.stderr)
    print(file=sys.stderr)

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit"):
            break
        if user_input.lower() == "/stats":
            stats = mt.get_stats()
            print(
                f"Memories: {stats.get('total_memories', 0)} | Events: {stats.get('total_events', 0)}"
            )
            continue
        if user_input.lower().startswith("/forget"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("Usage: /forget <entity_id>")
                continue
            try:
                mt.forget(uuid.UUID(parts[1].strip()))
                print("Forgotten.")
            except ValueError:
                print("Invalid UUID.")
            continue

        history.append({"role": "user", "content": user_input})

        try:
            response = call_fn(history, model, host, system, tools, timeout=120)
        except Exception as e:
            print(f"[Error: {e}]", file=sys.stderr)
            history.pop()
            continue

        content, tool_calls = extract_fn(response)

        # Handle tool calls: execute and feed results back
        while tool_calls:
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                result = _execute_tool(fn_name, fn_args, args.namespace)
                history.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc],
                    }
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result,
                    }
                )

            # Let LLM respond after tool results
            try:
                response = call_fn(history, model, host, system, tools, timeout=120)
            except Exception as e:
                print(f"[Error: {e}]", file=sys.stderr)
                break
            content, tool_calls = extract_fn(response)

        if content:
            print(content)

        history.append({"role": "assistant", "content": content or ""})
        if len(history) > 40:
            history = history[-40:]


def main():
    parser = argparse.ArgumentParser(description="MT Session — Auto-memory chat for any LLM")
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        default=os.environ.get("MT_SESSION_PROVIDER", "ollama"),
        help="LLM provider",
    )
    parser.add_argument("--model", help="Model name override")
    parser.add_argument("--host", help="Provider host override")
    parser.add_argument("--system", help="System prompt override")
    parser.add_argument("--namespace", default="session", help="MT namespace")
    args = parser.parse_args()
    run_session(args)


if __name__ == "__main__":
    main()
