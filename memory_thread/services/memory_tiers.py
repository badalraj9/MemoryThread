"""
Memory Tiers — Hot/Warm/Cold memory management.

Core:      Active context (high activation, recently accessed)
Episodic:  In-memory graph (all nodes, ~1ms access)
Semantic:  Summarized facts archived to PostgreSQL

A MemoryRouter scores nodes for tier placement.
A SummarizationPipeline consolidates threads into extracted facts.
"""

import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field

from memory_thread.config.settings import settings
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.content_resolver import resolve_content as _resolve_content
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class TieredNode:
    node_id: str
    tier: str  # "core" | "episodic" | "semantic"
    score: float
    content: str
    truth_score: float
    last_accessed: str
    importance: float  # 0.0-1.0 (combined centrality + truth)


class MemoryRouter:
    """
    Scores nodes for tier placement.
    Uses graph activation, recency, and topology.

    Policy:
      - score ≥ CORE_THRESHOLD  → core (inject into LLM context)
      - score ≥ EPISODIC_THRESHOLD → episodic (keep in graph)
      - score < EPISODIC_THRESHOLD → candidate for semantic archive
    """

    def score_node(self, node_id: str, current_activation: float = 0.0) -> float:
        """Score a node for tier placement. 0.0 = cold, 1.0 = hottest."""
        if not graph_engine._vertex_exists(node_id):
            return 0.0

        try:
            v = graph_engine.graph.vs.find(name=node_id)
        except (ValueError, KeyError):
            return 0.0

        vattrs = v.attributes()

        # 1. Activated score from current context (0.0-1.0)
        act_score = min(1.0, current_activation)

        # 2. Recency (higher = hotter)
        ts = vattrs.get("timestamp", "")
        recency = 0.0
        if ts:
            try:
                dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
                days_old = (datetime.utcnow() - dt).total_seconds() / 86400.0
                recency = max(0.0, 1.0 - (days_old / settings.TIERS_EPISODIC_DAYS))
            except (ValueError, TypeError):
                recency = 0.3
        else:
            recency = 0.3

        # 3. Topology (centrality + bridge)
        centrality = graph_engine.centrality(node_id)
        bridge = graph_engine.bridge_score(node_id)
        topology = min(1.0, (centrality * 2 + bridge * 3) / 5)

        # 4. Truth score
        def _sf(v, d=0.5):
            return float(v) if v is not None else d

        tv_conf = _sf(vattrs.get("truth_confidence"))
        tv_auth = _sf(vattrs.get("truth_authority"))
        truth = tv_conf * 0.4 + tv_auth * 0.35 + 0.25

        # Weighted combination
        score = act_score * 0.4 + recency * 0.25 + topology * 0.2 + truth * 0.15
        return min(1.0, max(0.0, score))

    def classify(self, node_id: str, current_activation: float = 0.0) -> str:
        """Return the appropriate tier for a node."""
        score = self.score_node(node_id, current_activation)
        if score >= settings.TIERS_ACTIVATION_CORE_THRESHOLD:
            return "core"
        if score >= settings.TIERS_ACTIVATION_EPISODIC_THRESHOLD:
            return "episodic"
        return "semantic"

    def get_core_context(self, active_node_ids: List[str], max_tokens: int = 2000) -> str:
        """Build a context string from core-tier nodes for LLM injection."""
        scored = []
        for nid in active_node_ids:
            score = self.score_node(nid, 1.0)
            if score >= settings.TIERS_ACTIVATION_CORE_THRESHOLD:
                content = self._resolve_content(nid)
                if content:
                    scored.append({"id": nid[:8], "content": content, "score": score})

        scored.sort(key=lambda x: -x["score"])
        lines = ["[Active Context]"]
        tokens = 3
        for item in scored:
            entry = f"- {item['content'][:120]}"
            est_tokens = len(entry) // 4
            if tokens + est_tokens > max_tokens:
                break
            lines.append(entry)
            tokens += est_tokens

        return "\n".join(lines)

    @staticmethod
    @staticmethod
    def _resolve_content(node_id: str) -> str:
        return _resolve_content(node_id)

    def get_tier_report(self) -> Dict[str, int]:
        """Return count of nodes in each tier."""
        counts = {"core": 0, "episodic": 0, "semantic": 0}
        for v in graph_engine.graph.vs:
            nid = v["name"]
            tier = self.classify(nid)
            counts[tier] = counts.get(tier, 0) + 1
        return counts


class SummarizationPipeline:
    """
    Consolidates thread events into extracted facts for the semantic tier.
    """

    def summarize_thread(self, thread_id: str) -> Optional[Dict]:
        """
        Summarize a thread's events into extracted, timeless facts.
        Returns a dict with extracted facts, or None if thread has no events.
        """
        from memory_thread.services.thread_service import thread_service

        result = thread_service.get_thread(thread_id)
        if not result or len(result.events) < 3:
            return None

        events = result.events
        content_lines = [f"[{e.get('actor', '?')}] {e.get('content', '')}" for e in events]

        summary_text = self._llm_summarize(content_lines)

        facts = []
        for line in summary_text.split("\n"):
            line = line.strip().lstrip("- ")
            if line and len(line) > 10:
                facts.append(
                    {
                        "content": line[:200],
                        "source_thread": thread_id,
                        "summarized_at": datetime.utcnow().isoformat(),
                        "source_event_count": len(events),
                    }
                )

        return {
            "thread_id": thread_id,
            "original_title": result.thread.title,
            "fact_count": len(facts),
            "facts": facts,
            "summarized_at": datetime.utcnow().isoformat(),
        }

    def _llm_summarize(self, content_lines: List[str]) -> str:
        """
        Summarize event lines into extracted facts.
        Uses heuristic extraction by default.
        """
        text = "\n".join(content_lines)

        # Simple fact extraction: deduplicate significant statements
        seen = set()
        facts = []
        for line in content_lines:
            # Extract the content part after "[actor]"
            parts = line.split("]", 1)
            content = parts[-1].strip() if len(parts) > 1 else line

            # Simple significance heuristic: longer statements = more informative
            if len(content) > 20 and content not in seen:
                seen.add(content)
                facts.append(content[:200])

        if not facts:
            return text[:500]

        return "\n".join(facts[:10])

    def archive_thread_to_semantic(self, thread_id: str, pg=None) -> Optional[Dict]:
        """
        Summarize a thread and store the facts in PostgreSQL.
        Returns the summary dict.
        """
        summary = self.summarize_thread(thread_id)
        if not summary:
            return None

        if pg:
            try:
                pg.execute(
                    """
                    INSERT INTO insights_log (timestamp, reflection_json)
                    VALUES (%s, %s)
                """,
                    (datetime.utcnow(), json.dumps(summary)),
                )
            except Exception as e:
                log.warning(f"Could not store summary: {e}")

        log.info(
            "Archived thread %s to semantic tier (%d facts)", thread_id[:8], summary["fact_count"]
        )
        return summary


memory_router = MemoryRouter()
summarization = SummarizationPipeline()
