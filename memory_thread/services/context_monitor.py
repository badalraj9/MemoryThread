"""
Context Monitor — Proactive context injection for AI agents.

Observes agent activity, extracts entity mentions, activates the
graph, and injects relevant context into the agent's prompt without
requiring an explicit query.

This is the key difference between a memory database (waits for query)
and a memory system (surfaces what's relevant without being asked).
"""

import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field

from memory_thread.config.settings import settings
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.content_resolver import resolve_content as _resolve_content
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class InjectedItem:
    """Tracks what was injected and when."""

    node_id: str
    content: str
    score: float
    turn: int


class ContextMonitor:
    """
    Observes agent activity and surfaces relevant graph context.

    Usage:
        monitor = ContextMonitor()
        agent_text = agent.last_response()
        context = monitor.observe(agent_text)
        full_prompt = context + original_prompt + agent_text
    """

    def __init__(self):
        self.active_seeds: Set[str] = set()
        self.injected: Dict[str, InjectedItem] = {}
        self.turn: int = 0

    def observe(self, agent_text: str, max_tokens: Optional[int] = None) -> str:
        """
        Given the agent's current text:
        1. Extract entity mentions
        2. Activate graph from seeds
        3. Format + deduplicate
        4. Return context string to prepend to prompt

        Returns empty string if no relevant context found.
        """
        if not settings.CONTEXT_INJECTION_ENABLED:
            return ""

        if not graph_engine.is_built or graph_engine.graph.vcount() == 0:
            return ""

        self.turn += 1
        max_tokens = max_tokens or settings.CONTEXT_INJECTION_MAX_TOKENS

        seeds = self._extract_entities(agent_text)
        if not seeds:
            return ""

        activated = graph_engine.activation(
            seeds=seeds,
            max_depth=settings.CONTEXT_INJECTION_MAX_DEPTH,
            decay_per_hop=settings.CONTEXT_INJECTION_DECAY,
            truth_threshold=settings.CONTEXT_INJECTION_ACTIVATION_THRESHOLD,
        )

        new_items = self._prepare_new_items(activated)
        if not new_items:
            return ""

        context = self._format_context(new_items, max_tokens)
        return context

    def _extract_entities(self, text: str) -> List[str]:
        """Extract entity mentions from agent text using graph content search."""
        if not text or not text.strip():
            return []

        words = text.lower().split()
        seeds = set()

        for word in words[:50]:
            cleaned = word.strip(".,!?;:'\"()[]{}").strip()
            if len(cleaned) < 3:
                continue
            matches = graph_engine.search_nodes(cleaned, attr="content")
            seeds.update(matches[:3])

        # Also try explicit UUID
        for word in words[:10]:
            try:
                import uuid

                uid = uuid.UUID(word.strip(".,!?;:'\"()[]{}"))
                if graph_engine._vertex_exists(str(uid)):
                    seeds.add(str(uid))
            except (ValueError, AttributeError):
                pass

        self.active_seeds = set(list(seeds)[: settings.CONTEXT_INJECTION_MAX_SEEDS])
        return list(self.active_seeds)

    def _prepare_new_items(self, activated: Dict[str, float]) -> List[Dict]:
        """Score activated nodes, deduplicate against already-injected."""
        new_items = []
        for node_id, activation_score in sorted(activated.items(), key=lambda x: -x[1]):
            if node_id in self.injected:
                continue
            if activation_score < settings.CONTEXT_INJECTION_ACTIVATION_THRESHOLD:
                continue

            content = self._resolve_content(node_id)
            if not content:
                continue

            new_items.append(
                {
                    "node_id": node_id,
                    "content": content,
                    "score": round(activation_score, 3),
                    "turn": self.turn,
                }
            )

            self.injected[node_id] = InjectedItem(
                node_id=node_id,
                content=content,
                score=activation_score,
                turn=self.turn,
            )

        self._prune_stale()
        return new_items

    def _resolve_content(self, node_id: str) -> str:
        """Get content string for a node, resolving entities to latest event."""
        return _resolve_content(node_id)

    def _format_context(self, items: List[Dict], max_tokens: int) -> str:
        """Format activated context for injection into prompt."""
        if not items:
            return ""

        lines = ["[Relevant Context]"]
        token_count = 3

        for item in items:
            entry = f"- {item['content'][:150]} (relevance: {item['score']:.0%})"
            est_tokens = len(entry) // 4
            if token_count + est_tokens > max_tokens:
                break
            lines.append(entry)
            token_count += est_tokens

        lines.append("")
        result = "\n".join(lines)
        log.debug("ContextMonitor injected %d items (%d tokens)", len(items), token_count)
        return result

    def _prune_stale(self):
        """Remove stale injections (not re-activated for N turns)."""
        stale = [
            nid
            for nid, item in self.injected.items()
            if self.turn - item.turn > settings.CONTEXT_INJECTION_STALE_TURNS
        ]
        for nid in stale:
            del self.injected[nid]

    def get_active_topics(self) -> List[str]:
        """Return currently tracked active topics."""
        return list(self.active_seeds)[:10]

    def get_stats(self) -> Dict:
        """Return injection statistics."""
        return {
            "turn": self.turn,
            "active_seeds": len(self.active_seeds),
            "injected_count": len(self.injected),
            "enabled": settings.CONTEXT_INJECTION_ENABLED,
        }

    def reset_session(self):
        """Reset for a new conversation session."""
        self.active_seeds.clear()
        self.injected.clear()
        self.turn = 0
        log.info("ContextMonitor session reset")


context_monitor = ContextMonitor()
